"""Independent review cases. Synthetic inputs and injected loopback only."""

import pytest

from metasocli_py.images import workflow as iw
from metasocli_py.persistence.files import read_json
from metasocli_py.providers.http import Http, ProviderError
from metasocli_py.providers.metaso import Metaso
from metasocli_py.providers.yiciyuang import Yiciyuang
from metasocli_py.video.capacity import Capacity
from metasocli_py.video.execution import ExecutionOptions, run_video
from metasocli_py.video.planning import prepare
from metasocli_py.video.retry import authorize_retry
from tests.fake_http import FakeProvider
from tests.test_image_http import image_story
from tests.test_video_http import text_story


@pytest.mark.asyncio
async def test_new_scope_refreshes_same_story_old_task_ids(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = text_story(tmp_path, 5)
    def selection(ids):
        return {'schemaVersion': 1, 'episodes': [{'episodeId': 'ep-1', 'segmentIds': ids}]}
    first = prepare(root, selected=selection(['s1', 's2', 's3', 's4']))
    next_plan = prepare(root, selected=selection(['s5']))
    runtime = tmp_path/'runtime'
    with FakeProvider() as fake:
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic-review')
        try:
            original = await run_video(root, first['batchId'], provider=provider, runtime=runtime,
                confirm=True, options=ExecutionOptions(submit_only=True))
            assert all(s['status'] == 'queued' for s in original['segments'])
            # The original process has stopped; remote IDs now return completed.
            assert len(fake.tasks) == 4 and fake.query_status == 'completed'
            result = await run_video(root, next_plan['batchId'], provider=provider, runtime=runtime,
                confirm=True, options=ExecutionOptions(max_polls=1, capacity_wait=.15, capacity_poll=.01))
            observed = {'phase': result['phase'], 'newPostCount': len(fake.requests)-4,
                'queryPaths': [g['path'] for g in fake.gets],
                'held': sum(s['capacity']['state']=='held' for s in Capacity(runtime).read()['slots'].values())}
            assert result['phase'] == 'complete', observed
        finally:
            await provider.http.close()


@pytest.mark.asyncio
async def test_explicit_retry_after_correcting_auth_can_submit_once(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = text_story(tmp_path, 1)
    plan = prepare(root, ['ep-1'])
    with FakeProvider() as fake:
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic-review')
        actual_create = provider.create
        async def reject(*args, **kwargs):
            raise ProviderError('PROVIDER_HTTP', 'Provider returned HTTP 401.', status=401, rejected=True)
        monkeypatch.setattr(provider, 'create', reject)
        try:
            result = await run_video(root, plan['batchId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
            operation = result['segments'][0]['operationId']
            assert result['segments'][0]['status'] == 'failed'
            monkeypatch.setattr(provider, 'create', actual_create)
            grant = authorize_retry(root, plan['batchId'], operation, True, False)
            result = await run_video(root, plan['batchId'], provider=provider, runtime=tmp_path/'runtime', resume=True,
                options=ExecutionOptions(max_polls=1, capacity_wait=.15, capacity_poll=.01))
            assert result['phase'] == 'complete', {'phase':result['phase'], 'blocker':result.get('blocker'),
                'postCount':len(fake.requests), 'newOperationId':grant['newOperationId']}
            assert len(fake.requests) == 1
        finally:
            await provider.http.close()


@pytest.mark.asyncio
async def test_image_quota_intent_window_has_durable_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = image_story(tmp_path, 1)
    profile = {'firstFrameSize':'1920x1088', 'providerLimits':
        {'concurrent':1, 'source':'synthetic offline review', 'checkedAt':'2026-11-13T00:00:00Z'}}
    plan = iw.plan_images(root, assets=['asset-0'], profile=profile)
    original_save = iw.save_job
    class SimulatedCrash(BaseException):
        pass
    def fail_before_job_write(*args, **kwargs):
        raise SimulatedCrash()
    with FakeProvider() as fake:
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic-review')
        try:
            monkeypatch.setattr(iw, 'save_job', fail_before_job_write)
            with pytest.raises(SimulatedCrash):
                await iw.run_images(root, plan['planId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
            monkeypatch.setattr(iw, 'save_job', original_save)
            assert len(fake.requests) == 0 and iw.image_jobs(root) == []
            result = await iw.run_images(root, plan['planId'], provider=provider, runtime=tmp_path/'runtime', resume=True,
                capacity_wait=.15, capacity_poll=.01)
            ledger = read_json(tmp_path/'runtime/images/yiciyuang-default/ledger.json')
            assert result['complete'], {'complete':result['complete'], 'items':result['items'],
                'postCount':len(fake.requests), 'quotaStates':[j['status'] for j in ledger['jobs'].values()]}
        finally:
            await provider.http.close()
