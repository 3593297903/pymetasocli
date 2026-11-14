import asyncio
from argparse import Namespace

import pytest

from metasocli_py.domain.errors import AppError
from metasocli_py.persistence.codec import sha256
from metasocli_py.persistence.files import write_json
from metasocli_py.providers.http import Http
from metasocli_py.providers.metaso import Metaso
from metasocli_py.video.capacity import Capacity
from metasocli_py.video.context_ir import ir_command
from metasocli_py.video.execution import ExecutionOptions, run_video
from metasocli_py.video.planning import prepare
from tests.fake_http import FakeProvider
from tests.test_video_http import text_story


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [False, True])
async def test_query_failure_releases_poll_limit_holds(tmp_path, monkeypatch, failure):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = text_story(tmp_path, 1)
    plan = prepare(root, ['ep-1'])
    with FakeProvider() as fake:
        fake.query_error = failure
        fake.query_status = 'running'
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        result = await run_video(root, plan['batchId'], provider=provider, runtime=tmp_path/'runtime', confirm=True,
                                 options=ExecutionOptions(max_polls=1, poll_seconds=0))
        cap = next(iter(Capacity(tmp_path/'runtime').read()['slots'].values()))['capacity']
        assert cap['state'] == ('released' if failure else 'held')
        assert result['segments'][0]['error']['code'] == ('PROVIDER_HTTP' if failure else 'POLL_LIMIT')
        await provider.http.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('limit', [1, 4])
async def test_two_stories_priority_and_spare_capacity(tmp_path, monkeypatch, limit):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    for name in ('a', 'b'):
        (tmp_path/name).mkdir()
    a, b = text_story(tmp_path/'a', 6), text_story(tmp_path/'b', 4)
    pa, pb = prepare(a, ['ep-1'], concurrency=limit), prepare(b, ['ep-1'])
    runtime = tmp_path/'runtime'
    with FakeProvider() as fake:
        fake.create_delay = .3
        p1 = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        p2 = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        opts = ExecutionOptions(max_polls=1, poll_seconds=0, capacity_wait=5, capacity_poll=.01)
        task = asyncio.create_task(run_video(a, pa['batchId'], provider=p1, runtime=runtime, confirm=True, options=opts))
        while not fake.requests:
            await asyncio.sleep(.01)
        other = asyncio.create_task(run_video(b, pb['batchId'], provider=p2, runtime=runtime, confirm=True, options=opts))
        results = await asyncio.gather(task, other)
        assert all(r['phase'] == 'complete' for r in results), results
        ledger = Capacity(runtime).read()
        a_tasks = {s['taskId'] for s in ledger['slots'].values() if s['projectId'] == pa['projectId']}
        creates = [identifier for event, identifier, _ in fake.events if event == 'create']
        assert fake.max_live <= 4
        if limit == 4:
            # Server accept/handler order can differ from actual dispatch order.
            assert set(creates[:4]).issubset(a_tasks)
            from metasocli_py.video.store import find_jobs
            a_sends = sorted(j['timings']['send'] for j in find_jobs(a))
            b_sends = sorted(j['timings']['send'] for j in find_jobs(b))
            assert a_sends[5] < b_sends[0]
        else:
            assert sum(x in a_tasks for x in creates[:4]) == 1
        await p1.http.close()
        await p2.http.close()


@pytest.mark.asyncio
async def test_explicit_ir_review_derive_video_false(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = text_story(tmp_path, 1)
    plan = prepare(root, ['ep-1'], workflow='h3-context-ir')
    args = Namespace(action='run', plan=plan['batchId'], segment='s1', confirm=True, operation=None, file=None)
    with FakeProvider() as fake:
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        record = await ir_command(root, args, provider)
        assert record['status'] == 'enhanced'
        assert fake.requests[0]['path'].endswith('/h3_context_ir')
        review = {'schemaVersion': 1, 'operationId': record['operationId'], 'promptHash': record['promptHash'],
            'verdict': 'approved', 'reviewer': 'synthetic-test', 'dialogueQuotes': [],
            'findings': {key: 'Synthetic fixture retains original content.' for key in ('dialogue', 'references', 'narration', 'constraints')}}
        file = tmp_path/'review.json'
        write_json(file, review)
        args.operation, args.action, args.file = record['operationId'], 'review', file
        await ir_command(root, args, None)
        args.action = 'derive'
        derived = await ir_command(root, args, None)
        result = await run_video(root, derived['planId'], provider=provider, runtime=tmp_path/'runtime', confirm=True,
                                 options=ExecutionOptions(max_polls=1))
        assert result['phase'] == 'complete'
        assert len(fake.requests) == 2
        assert fake.requests[1]['fields']['context_ir_enabled'] is False
        assert sha256(fake.requests[1]['fields']['content'][0]['text']) == record['promptHash']
        review['dialogueQuotes'] = ['made up absent quote']
        write_json(file, review)
        args.action = 'review'
        with pytest.raises(AppError):
            await ir_command(root, args, None)
        await provider.http.close()
