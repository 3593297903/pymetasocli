"""Recovery scheduling on synthetic HTTP; counts include every actual request."""
import asyncio
import json
import time
from pathlib import Path

import pytest

from metasocli_py.persistence.files import lock
from metasocli_py.providers.http import Http
from metasocli_py.providers.metaso import Metaso
from metasocli_py.video.capacity import Capacity
from metasocli_py.video.execution import ExecutionOptions, observe_once, publish_event, run_video
from metasocli_py.video.planning import prepare
from metasocli_py.video.retry import authorize_retry
from metasocli_py.video.store import load_job, save_job
from tests.fake_http import FakeProvider
from tests.test_video_http import text_story


def selected(*ids):
    return {'schemaVersion': 1, 'episodes': [{'episodeId': 'ep-1', 'segmentIds': list(ids)}]}


def options(**changes):
    return ExecutionOptions(**{'max_polls': 1, 'capacity_wait': .2, 'capacity_poll': .01, **changes})


def report(name, data):
    path = Path(__file__).resolve().parents[1]/'.work/reports'/f'repair-{name}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


@pytest.mark.asyncio
async def test_normal_schedule_has_no_additional_history_gets(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root, runtime = text_story(tmp_path, 2), tmp_path/'runtime'
    plan = prepare(root, ['ep-1'])
    with FakeProvider() as fake:
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            result = await run_video(root, plan['batchId'], provider=provider, runtime=runtime, confirm=True, options=options())
            assert result['phase'] == 'complete' and len(fake.requests) == 2
            assert len(fake.gets) == 4
            assert len([g for g in fake.gets if '/query/' in g['path']]) == 2
            report('normal-scheduler', {'postCount': 2, 'selectedGetCount': 2, 'historicalGetCount': 0,
                'downloadGetCount': 2, 'elapsedMs': result['timings']['executeMs'], 'events': fake.events})
        finally:
            await provider.http.close()


@pytest.mark.asyncio
async def test_history_parallel_refill_only_selected_delivery(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = text_story(tmp_path, 5)
    old = prepare(root, selected=selected('s1', 's2', 's3', 's4'))
    new = prepare(root, selected=selected('s5'))
    runtime = tmp_path/'runtime'
    with FakeProvider() as fake:
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            await run_video(root, old['batchId'], provider=provider, runtime=runtime, confirm=True, options=options(submit_only=True))
            assert not fake.gets
            fake.query_delays = {'1': .1, '2': 1.2, '3': 1.2, '4': 1.2}
            began = time.perf_counter()
            result = await run_video(root, new['batchId'], provider=provider, runtime=runtime, confirm=True, options=options())
            elapsed = (time.perf_counter()-began)*1000
            assert result['phase'] == 'complete'
            assert [s['segmentId'] for s in result['segments']] == ['s5']
            assert len(fake.requests) == 5 and fake.max_queries <= 4 and fake.max_queries >= 2
            paths = [g['path'] for g in fake.gets]
            assert paths.count('/video/5') == 1
            assert not any(p in paths for p in ['/video/1', '/video/2', '/video/3', '/video/4'])
            assert all(paths.count('/api/minimax/v2/query/video_generation/'+str(i)) == 1 for i in range(1, 6))
            sent5 = fake.requests[4]['time']
            slow_completions = [t for event, i, t in fake.events if event == 'terminal' and i in ('2', '3', '4')]
            assert all(sent5 < t for t in slow_completions)
            first_terminal = next(t for event, i, t in fake.events if event == 'terminal' and i == '1')
            report('scheduler', {'additionalPostCount': 1, 'historicalGetCount': 4, 'selectedGetCount': 1,
                'historicalDownloadCount': 0, 'maxParallelGet': fake.max_queries, 'elapsedMs': elapsed,
                'terminalToRefillMs': (sent5-first_terminal)*1000, 'getRequests': fake.gets,
                'events': fake.events, 'newPostStartedBeforeSlowHistoricalResponses': True})
        finally:
            await provider.http.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['running', 'budget-zero', 'get-failure', 'wrong-id', 'live-owner', 'other-story'])
async def test_history_r3_boundaries(tmp_path, monkeypatch, mode):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    runtime = tmp_path/'runtime'
    root = text_story(tmp_path, 5)
    old = prepare(root, selected=selected('s1', 's2', 's3', 's4'))
    newroot = text_story(tmp_path, 1, name='other') if mode == 'other-story' else root
    new = prepare(newroot, selected=selected('s1' if mode == 'other-story' else 's5'))
    with FakeProvider() as fake:
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            original = await run_video(root, old['batchId'], provider=provider, runtime=runtime, confirm=True, options=options(submit_only=True))
            operations = [s['operationId'] for s in original['segments']]
            fake.query_status = 'running'
            fake.query_error = mode == 'get-failure'
            if mode == 'wrong-id':
                fake.query_ids = {str(i): 'incorrect-id' for i in range(1, 5)}
            from contextlib import ExitStack
            with ExitStack() as leases:
                if mode == 'live-owner':
                    for operation in operations:
                        leases.enter_context(lock(runtime/'owners'/f'{operation}.lock'))
                result = await run_video(newroot, new['batchId'], provider=provider, runtime=runtime, confirm=True,
                                         options=options(max_polls=0 if mode == 'budget-zero' else 1, download_results=False))
            caps = Capacity(runtime).read()['slots']
            released = mode in ('get-failure', 'wrong-id')
            assert all(caps[o]['capacity']['state'] == ('released' if released else 'held') for o in operations)
            assert all(not caps[o]['capacity']['terminal'] for o in operations)
            assert len(fake.requests) == (5 if released else 4)
            if mode in ('other-story', 'budget-zero', 'live-owner'):
                assert fake.gets == []
            else:
                assert len([g for g in fake.gets if any(g['path'].endswith('/'+str(i)) for i in range(1, 5))]) == 4
            if released:
                assert all(caps[o]['capacity']['reason'] == 'query_unavailable' for o in operations)
                assert all(caps[o]['taskId'] != 'incorrect-id' for o in operations)
            assert len(result['segments']) == 1
        finally:
            await provider.http.close()


@pytest.mark.asyncio
async def test_selected_dedup_and_late_active_cannot_overwrite_terminal(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root, runtime = text_story(tmp_path, 2), tmp_path/'runtime'
    first = prepare(root, selected=selected('s1'))
    both = prepare(root, ['ep-1'])
    with FakeProvider() as fake:
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            saved = await run_video(root, first['batchId'], provider=provider, runtime=runtime, confirm=True, options=options(submit_only=True))
            result = await run_video(root, both['batchId'], provider=provider, runtime=runtime, confirm=True, options=options())
            assert result['phase'] == 'complete'
            assert sum(g['path'].endswith('/query/video_generation/1') for g in fake.gets) == 1
            operation = saved['segments'][0]['operationId']
            job = load_job(root, operation)
            cap = Capacity(runtime)
            before = cap.read()['slots'][operation]['capacity']
            # Model a GET issued before another durable terminal publication.
            async def late_active(*args):
                latest = load_job(root, operation)
                latest['status'] = 'generated'
                save_job(root, latest)
                publish_event(root, cap, latest, 'provider_terminal', 1)
                return {'status': 'running', 'taskId': job['taskId']}
            monkeypatch.setattr(provider, 'query', late_active)
            await observe_once(root, job, cap, provider, asyncio.Semaphore(4), options(), asyncio.Event())
            assert job['status'] == 'generated'
            after = cap.read()['slots'][operation]['capacity']
            assert after['terminal'] and after['state'] == 'released' and after['applied'] >= before['applied']
        finally:
            await provider.http.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('code', [401, 402, 403])
async def test_auth_fixed_original_scope_and_exactly_once_retry(tmp_path, monkeypatch, code):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root, runtime = text_story(tmp_path, 3), tmp_path/'runtime'
    plan = prepare(root, ['ep-1'], concurrency=1)
    with FakeProvider() as fake:
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            fake.video_reject_status = code
            first = await run_video(root, plan['batchId'], provider=provider, runtime=runtime, confirm=True, options=options())
            failed = first['segments'][0]['operationId']
            assert len(fake.requests) == 1 and first['blocker']['code'] == 'PROVIDER_AUTHORIZATION'
            fake.video_reject_status = None
            rest = await run_video(root, plan['batchId'], provider=provider, runtime=runtime, resume=True, options=options())
            assert len(fake.requests) == 3 and rest['segments'][0]['status'] == 'failed'
            assert all(s['status'] == 'downloaded' for s in rest['segments'][1:])
            grant = authorize_retry(root, plan['batchId'], failed, True, False)
            assert grant == authorize_retry(root, plan['batchId'], failed, True, False)
            final = await run_video(root, plan['batchId'], provider=provider, runtime=runtime, resume=True, options=options())
            assert final['phase'] == 'complete' and len(fake.requests) == 4
            assert final['segments'][0]['operationId'] == grant['newOperationId']
            assert load_job(root, failed)['error']['httpStatus'] == code
            await run_video(root, plan['batchId'], provider=provider, runtime=runtime, resume=True, options=options())
            assert len(fake.requests) == 4
            report(f'auth-{code}', {'initialRejectedPosts': 1, 'remainingOriginalPosts': 2, 'explicitRetryPosts': 1,
                'repeatResumePosts': 0, 'credentialValidationGets': 0})
        finally:
            await provider.http.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('code', [401, 402, 403])
async def test_new_retry_rejection_stops_this_invocation(tmp_path, monkeypatch, code):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root, runtime = text_story(tmp_path, 2), tmp_path/'runtime'
    plan = prepare(root, ['ep-1'], concurrency=1)
    with FakeProvider() as fake:
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            fake.video_reject_status = code
            first = await run_video(root, plan['batchId'], provider=provider, runtime=runtime, confirm=True, options=options())
            authorize_retry(root, plan['batchId'], first['segments'][0]['operationId'], True, False)
            again = await run_video(root, plan['batchId'], provider=provider, runtime=runtime, resume=True, options=options())
            assert len(fake.requests) == 2 and again['blocker']['code'] == 'PROVIDER_AUTHORIZATION'
            assert again['segments'][1]['status'] == 'pending'
        finally:
            await provider.http.close()
