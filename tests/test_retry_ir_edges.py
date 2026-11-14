from argparse import Namespace

import pytest

from metasocli_py.application.story import STATE, replace_prompt
from metasocli_py.domain.errors import AppError
from metasocli_py.persistence.codec import sealed
from metasocli_py.persistence.files import read_json, write_json
from metasocli_py.providers.http import Http
from metasocli_py.providers.metaso import Metaso
from metasocli_py.video.context_ir import ir_command
from metasocli_py.video.execution import ExecutionOptions, receipt_path, run_video
from metasocli_py.video.planning import prepare
from metasocli_py.video.retry import authorize_retry
from metasocli_py.video.store import load_job
from tests.fake_http import FakeProvider
from tests.test_video_http import text_story


@pytest.mark.asyncio
async def test_unknown_late_id_obsolete_grant_and_known_failure_retry(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = text_story(tmp_path, 1)
    plan = prepare(root)
    with FakeProvider() as fake:
        fake.fail_video = True
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        options = ExecutionOptions(max_polls=1, poll_seconds=0, capacity_poll=.01)
        result = await run_video(root, plan['batchId'], provider=provider, runtime=tmp_path/'runtime', confirm=True, options=options)
        a = load_job(root, result['segments'][0]['operationId'])
        grant_b = authorize_retry(root, plan['batchId'], a['operationId'], True, True)
        authfile = root/STATE/'retries'/f'{a["operationId"]}.json'
        authbytes = authfile.read_bytes()
        write_json(receipt_path(root, a['operationId'], 'create'), sealed({
            **{k: a[k] for k in ('operationId', 'projectId', 'requestHash')}, 'taskId': '1', 'receivedAt': 'synthetic'}))
        fake.query_status = 'failed'
        await run_video(root, plan['batchId'], provider=provider, runtime=tmp_path/'runtime', resume=True, options=options)
        assert load_job(root, grant_b['newOperationId'])['error']['code'] == 'RETRY_SUPERSEDED'
        assert load_job(root, a['operationId'])['status'] == 'failed'
        assert len(fake.requests) == 1
        grant_c = authorize_retry(root, plan['batchId'], a['operationId'], True, False)
        assert grant_c['attempt'] == 3
        fake.fail_video, fake.query_status = False, 'completed'
        result = await run_video(root, plan['batchId'], provider=provider, runtime=tmp_path/'runtime', resume=True, options=options)
        assert result['phase'] == 'complete' and len(fake.requests) == 2
        assert authorize_retry(root, plan['batchId'], a['operationId'], True, True) == grant_b
        assert read_json(root/STATE/'batches'/plan['batchId']/'run.json')['items'][0]['operationId'] == grant_c['newOperationId']
        assert authorize_retry(root, plan['batchId'], a['operationId'], True, False) == grant_c
        await run_video(root, plan['batchId'], provider=provider, runtime=tmp_path/'runtime', resume=True, options=options)
        assert len(fake.requests) == 2 and authfile.read_bytes() == authbytes
        # Missing retry state plus any submission evidence must never recreate it.
        (root/STATE/'jobs'/f'{grant_c["newOperationId"]}.json').unlink()
        with pytest.raises(AppError) as caught:
            authorize_retry(root, plan['batchId'], a['operationId'], True, False)
        assert caught.value.code == 'RETRY_EVIDENCE_CONFLICT'
        await provider.http.close()


@pytest.mark.asyncio
async def test_ir_rebind_equivalent_segment_and_preserve_old_derived_plan(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = text_story(tmp_path, 2)
    original = prepare(root, workflow='h3-context-ir')
    args = Namespace(action='run', plan=original['batchId'], segment='s1', confirm=True, operation=None,
                     file=None, submit_only=False, max_polls=1, poll_ms=0)
    with FakeProvider() as fake:
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        record = await ir_command(root, args, provider)
        review = {'schemaVersion': 1, 'operationId': record['operationId'], 'promptHash': record['promptHash'],
                  'verdict': 'approved', 'reviewer': 'synthetic reviewer', 'dialogueQuotes': [],
                  'findings': {k: 'synthetic reviewed' for k in ('dialogue', 'references', 'narration', 'constraints')}}
        args.operation, args.file, args.action = record['operationId'], tmp_path/'review.json', 'review'
        write_json(args.file, review)
        await ir_command(root, args, None)
        args.action = 'derive'
        old = await ir_command(root, args, None)
        oldfile = root/STATE/'batches'/old['planId']/'plan.json'
        oldbytes = oldfile.read_bytes()
        replacement = tmp_path/'replacement.txt'
        replacement.write_text('另一个镜头的完整新内容。', encoding='utf-8')
        replace_prompt(root, 'ep-1', 's2', replacement)
        new = prepare(root, workflow='h3-context-ir')
        assert new['batchId'] != original['batchId']
        args.plan, args.action = new['batchId'], 'run'
        assert (await ir_command(root, args, provider))['operationId'] == record['operationId']
        assert len(fake.requests) == 1
        args.action = 'review'
        await ir_command(root, args, None)
        args.action = 'derive'
        derived = await ir_command(root, args, None)
        assert derived['planId'] != old['planId'] and oldfile.read_bytes() == oldbytes
        assert (await ir_command(root, args, None))['planId'] == derived['planId']
        args.action = 'review'
        write_json(args.file, {**review, 'reviewer': 'changed'})
        with pytest.raises(AppError):
            await ir_command(root, args, None)
        await provider.http.close()


@pytest.mark.asyncio
async def test_ir_complete_response_and_result_recover_without_post(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = text_story(tmp_path, 1)
    plan = prepare(root, workflow='h3-context-ir')
    args = Namespace(action='run', plan=plan['batchId'], segment='s1', confirm=True, operation=None,
                     file=None, submit_only=True, max_polls=1, poll_ms=0)
    with FakeProvider() as fake:
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        record = await ir_command(root, args, provider)
        path = root/STATE/'context-ir'/record['operationId']/'operation.json'
        damaged = read_json(path)
        damaged.pop('taskId')
        damaged['status'] = 'submitting'
        write_json(path, sealed(damaged))
        args.operation, args.action, args.submit_only = record['operationId'], 'resume', False
        resumed = await ir_command(root, args, provider)
        assert resumed['status'] == 'enhanced' and len(fake.requests) == 1
        # Simulate the result receipt being durable before its state update.
        resumed['status'] = 'queued'
        resumed.pop('resultPath')
        resumed.pop('promptHash')
        write_json(path, sealed(resumed))
        gets = len(fake.gets)
        final = await ir_command(root, args, provider)
        assert final['status'] == 'enhanced' and len(fake.gets) == gets and len(fake.requests) == 1
        await provider.http.close()


def test_real_ffmpeg_av_validation(tmp_path):
    import subprocess

    from metasocli_py.media.av import verify_av
    from metasocli_py.media.inspect import video_info
    video = tmp_path/'av.mp4'
    result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=432x768:r=5:d=4',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000:duration=4', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-shortest', str(video)], capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert verify_av(video, video_info(video)['sha256']) == {'passed': True}
    assert not verify_av(video, '0'*64)['passed']
