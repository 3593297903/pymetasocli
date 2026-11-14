from argparse import Namespace

import pytest

from metasocli_py.application.story import STATE, import_story, initialize
from metasocli_py.domain.errors import AppError
from metasocli_py.images.workflow import image_jobs, plan_images, run_images
from metasocli_py.persistence.codec import digest, sealed
from metasocli_py.persistence.files import read_json, write_json
from metasocli_py.providers.http import Http
from metasocli_py.providers.metaso import Metaso
from metasocli_py.providers.yiciyuang import Yiciyuang
from metasocli_py.video.capacity import Capacity, apply_decision
from metasocli_py.video.execution import ExecutionOptions, run_video
from metasocli_py.video.planning import prepare
from metasocli_py.video.retry import authorize_retry
from metasocli_py.video.single import single_command
from tests.fake_http import FakeProvider
from tests.test_image_http import image_story
from tests.test_image_recovery import PROFILE
from tests.test_video_http import text_story


@pytest.mark.asyncio
async def test_url_two_download_lanes_and_local_reports(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = image_story(tmp_path, 8)
    plan = plan_images(root, assets=[f'asset-{i}' for i in range(8)], profile=PROFILE)
    with FakeProvider() as fake:
        fake.image_url, fake.download_delay = True, .25
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        result = await run_images(root, plan['planId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
        assert result['complete'] and result['lanes']['download']['observedPeak'] == 2
        assert 0 < result['lanes']['decode']['observedPeak'] <= 2
        assert result['lanes']['registration']['observedPeak'] == 1
        assert (root/result['indexPath']).is_file() and result['videoCheck']['ok']
        assert len(fake.requests) == 8 and len(fake.gets) == 8
        assert all('Authorization' not in r['headers'] for r in fake.gets)
        await provider.http.close()


@pytest.mark.asyncio
async def test_lost_image_job_with_receipt_never_posts_again(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = image_story(tmp_path, 1)
    plan = plan_images(root, assets=['asset-0'], profile=PROFILE)
    with FakeProvider() as fake:
        fake.status_code = 502
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        await run_images(root, plan['planId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
        job = image_jobs(root)[0]
        (root/STATE/'image-jobs'/f'{job["operationId"]}.json').unlink()
        with pytest.raises(AppError) as caught:
            await run_images(root, plan['planId'], provider=provider, runtime=tmp_path/'runtime', resume=True)
        assert caught.value.code == 'IMAGE_JOB_MISSING' and len(fake.requests) == 1
        await provider.http.close()


@pytest.mark.asyncio
async def test_image_request_resealed_tamper_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = image_story(tmp_path, 1)
    plan = plan_images(root, assets=['asset-0'], profile=PROFILE)
    with FakeProvider() as fake:
        fake.status_code = 502
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        await run_images(root, plan['planId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
        job = image_jobs(root)[0]
        job['input']['promptHash'] = '0'*64
        job['requestHash'] = digest(job['input'])
        job['inputHash'] = digest({'fingerprint': job['fingerprint'], 'input': job['input']})
        write_json(root/STATE/'image-jobs'/f'{job["operationId"]}.json', sealed(job))
        with pytest.raises(AppError) as caught:
            image_jobs(root)
        assert caught.value.code == 'IMAGE_JOB_IDENTITY' and len(fake.requests) == 1
        await provider.http.close()


@pytest.mark.asyncio
async def test_known_shared_image_limit_survives_unconfigured_second_profile(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    for name in ('a', 'b'):
        (tmp_path/name).mkdir()
    a, b = image_story(tmp_path/'a', 1), image_story(tmp_path/'b', 1)
    pa = plan_images(a, assets=['asset-0'], profile={**PROFILE, 'providerLimits': {'concurrent': 1, 'source': 'synthetic', 'checkedAt': 'synthetic'}})
    pb = plan_images(b, assets=['asset-0'], profile=PROFILE)
    with FakeProvider() as fake:
        fake.status_code = 502
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        await run_images(a, pa['planId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
        result = await run_images(b, pb['planId'], provider=provider, runtime=tmp_path/'runtime', confirm=True, capacity_wait=0)
        assert not result['complete'] and len(fake.requests) == 1
        await provider.http.close()


@pytest.mark.asyncio
async def test_manual_video_task_link_preserves_observed_terminal(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = text_story(tmp_path, 1)
    plan = prepare(root)
    with FakeProvider() as fake:
        fake.fail_video = True
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        result = await run_video(root, plan['batchId'], provider=provider, runtime=tmp_path/'runtime', confirm=True, options=ExecutionOptions(max_polls=1))
        operation = result['segments'][0]['operationId']
        fake.query_status = 'failed'
        args = Namespace(command='attach-task', operation=operation, confirm_task_link=True, task='1')
        await single_command(root, args, provider, tmp_path/'runtime')
        job = read_json(root/STATE/'jobs'/f'{operation}.json')
        assert job['status'] == 'failed' and Capacity(tmp_path/'runtime').read()['slots'][operation]['capacity']['terminal']
        with pytest.raises(AppError):
            await single_command(root, args, provider, tmp_path/'runtime')
        assert len(fake.requests) == 1
        await provider.http.close()


def test_observation_watermark_blocks_stale_running_and_terminal_absorbs():
    slot = {'operationId': 'op', 'projectId': 'project', 'requestHash': 'hash', 'taskId': 'task',
            'capacity': {'state': 'released', 'terminal': False, 'version': 1, 'issued': 3, 'applied': 1}}
    base = {'operationId': 'op', 'projectId': 'project', 'requestHash': 'hash', 'taskId': 'task'}
    assert not apply_decision(slot, {**base, 'sequence': 2, 'reason': 'remote_active_recovered'})
    assert slot['capacity']['state'] == 'released'
    assert apply_decision(slot, {**base, 'sequence': 1, 'reason': 'provider_terminal'})
    assert not apply_decision(slot, {**base, 'sequence': 3, 'reason': 'remote_active_recovered'})


@pytest.mark.asyncio
async def test_corrupt_output_does_not_strand_peer_and_missing_output_is_incomplete(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = text_story(tmp_path, 3)
    plan = prepare(root)
    runtime = tmp_path/'runtime'
    with FakeProvider() as fake:
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        first = await run_video(root, plan['batchId'], provider=provider, runtime=runtime, confirm=True, options=ExecutionOptions(submit_only=True))
        operation = first['segments'][0]['operationId']
        args = Namespace(command='resume', operation=operation)
        job = await single_command(root, args, provider, runtime)
        output = root/job['output']['path']
        damaged = bytearray(output.read_bytes())
        damaged[-1] ^= 1
        output.write_bytes(damaged)
        result = await run_video(root, plan['batchId'], provider=provider, runtime=runtime, resume=True, options=ExecutionOptions(poll_seconds=0))
        assert result['phase'] == 'partial' and result['segments'][0]['error']['code'] == 'OUTPUT_CHANGED'
        assert all(s.get('output') for s in result['segments'][1:])
        assert len(fake.requests) == 3 and output.read_bytes() == damaged
        output.rename(output.with_suffix('.held'))
        assert (await run_video(root, plan['batchId']))['phase'] == 'partial'
        result = await run_video(root, plan['batchId'], provider=provider, runtime=runtime, resume=True, options=ExecutionOptions(poll_seconds=0))
        assert result['phase'] == 'complete' and len(fake.requests) == 3
        await provider.http.close()


@pytest.mark.asyncio
async def test_register_missing_slot_and_old_source_error_cannot_undo_fresh_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = text_story(tmp_path, 1)
    plan = prepare(root)
    runtime = tmp_path/'runtime'
    with FakeProvider() as fake:
        fake.query_status = 'running'
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        result = await run_video(root, plan['batchId'], provider=provider, runtime=runtime, confirm=True, options=ExecutionOptions(max_polls=1))
        operation = result['segments'][0]['operationId']
        capacity = Capacity(runtime)
        ledger = capacity.read()
        del ledger['slots'][operation]
        capacity.save(ledger)
        await run_video(root, plan['batchId'], provider=provider, runtime=runtime, resume=True, options=ExecutionOptions(max_polls=1))
        assert capacity.read()['slots'][operation]['capacity']['state'] == 'held' and len(fake.requests) == 1
        receipt = root/STATE/'receipts'/f'{operation}-create.json'
        receipt.write_bytes(b'{')
        capacity.audit()
        slot = capacity.read()['slots'][operation]
        assert slot['capacity']['state'] == 'released'
        sequence = capacity.issue(operation)
        capacity.apply({**{k: slot[k] for k in ('operationId', 'projectId', 'requestHash', 'taskId')}, 'sequence': sequence, 'reason': 'remote_active_recovered'})
        capacity.audit()
        assert capacity.read()['slots'][operation]['capacity']['state'] == 'held'
        await provider.http.close()


@pytest.mark.asyncio
async def test_explicit_image_specification_blocks_only_conflicting_items(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = tmp_path/'specification'
    initialize(root, '规格校验')
    source = tmp_path/'source.txt'
    source.write_text('甲', encoding='utf-8')
    import_story(root, {'episodeId': 'ep', 'kind': 'video-prompts', 'source': str(source),
        'segments': [{'id': 's1', 'start': 0, 'end': 1, 'duration': 4}],
        'recipes': [{'assetId': f'asset-{i}', 'kind': 'first_frame', 'prompt': p}
                    for i, p in enumerate(['4K 首帧', '2K 首帧', '普通首帧'])]})
    selected = ['asset-0', 'asset-1', 'asset-2']
    plan = plan_images(root, assets=selected, profile=PROFILE)
    assert [i['action'] for i in plan['items']] == ['blocked', 'blocked', 'generate']
    with FakeProvider() as fake:
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        result = await run_images(root, plan['planId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
        assert len(fake.requests) == 1 and not result['complete']
        assert [i['status'] for i in result['items']] == ['blocked', 'blocked', 'registered']
        await provider.http.close()
    supported = plan_images(root, assets=selected, profile={**PROFILE, 'sizes': {'asset-0': '4096x4096', 'asset-1': '2560x1440'}})
    assert all(i['action'] != 'blocked' for i in supported['items'])


@pytest.mark.asyncio
async def test_released_same_story_unknown_does_not_block_different_segment(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = text_story(tmp_path, 2)
    def selected(segment):
        return {'schemaVersion': 1, 'episodes': [{'episodeId': 'ep-1', 'segmentIds': [segment]}]}
    a, b = prepare(root, selected=selected('s1')), prepare(root, selected=selected('s2'))
    with FakeProvider() as fake:
        fake.fail_video = True
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        failed = await run_video(root, a['batchId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
        assert failed['segments'][0]['status'] == 'submit_unknown'
        fake.fail_video = False
        result = await run_video(root, b['batchId'], provider=provider, runtime=tmp_path/'runtime', confirm=True, options=ExecutionOptions(poll_seconds=0))
        assert result['phase'] == 'complete' and len(fake.requests) == 2
        await run_video(root, a['batchId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
        assert len(fake.requests) == 2
        await provider.http.close()


@pytest.mark.asyncio
async def test_restricted_retry_expands_only_with_explicit_full_batch_authorization(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = text_story(tmp_path, 3)
    first = prepare(root, selected={'schemaVersion': 1, 'episodes': [{'episodeId': 'ep-1', 'segmentIds': ['s1']}]})
    whole = prepare(root)
    runtime, options = tmp_path/'runtime', ExecutionOptions(poll_seconds=0)
    with FakeProvider() as fake:
        fake.fail_video = True
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        lost = await run_video(root, first['batchId'], provider=provider, runtime=runtime, confirm=True, options=options)
        authorize_retry(root, whole['batchId'], lost['segments'][0]['operationId'], True, True)
        fake.fail_video = False
        for _ in range(2):
            result = await run_video(root, whole['batchId'], provider=provider, runtime=runtime, confirm=True, options=options)
            assert result['phase'] == 'partial' and len(fake.requests) == 2
        result = await run_video(root, whole['batchId'], provider=provider, runtime=runtime, confirm=True, full_scope=True, options=options)
        assert result['phase'] == 'complete' and len(fake.requests) == 4
        assert (root/STATE/'batches'/whole['batchId']/'full-authorization.json').is_file()
        await provider.http.close()
