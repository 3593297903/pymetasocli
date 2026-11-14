import json
import time
from pathlib import Path

import pytest

from metasocli_py.providers.http import Http
from metasocli_py.providers.metaso import Metaso
from metasocli_py.video.capacity import Capacity
from metasocli_py.video.execution import ExecutionOptions, run_video
from metasocli_py.video.planning import prepare
from metasocli_py.video.store import load_job
from tests.fake_http import FakeProvider
from tests.test_repair_video import selected
from tests.test_video_http import text_story


@pytest.mark.asyncio
async def test_round_budget_preserves_results_without_repeating_gets(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root, runtime = text_story(tmp_path, 5), tmp_path/'runtime'
    old = prepare(root, selected=selected('s1', 's2', 's3', 's4'))
    new = prepare(root, selected=selected('s5'))
    with FakeProvider() as fake:
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic', query_timeout=3)
        try:
            initial = await run_video(root, old['batchId'], provider=provider, runtime=runtime,
                                     confirm=True, options=ExecutionOptions(submit_only=True))
            fake.query_delays = {str(i): 1.2 for i in range(1, 5)}
            fake.query_status = 'running'
            began = time.perf_counter()
            result = await run_video(root, new['batchId'], provider=provider, runtime=runtime, confirm=True,
                                    options=ExecutionOptions(max_polls=3, capacity_wait=.15, capacity_poll=.01, poll_seconds=.01))
            elapsed = time.perf_counter()-began
            assert result['phase'] == 'partial' and len(fake.requests) == 4
            queries = [g for g in fake.gets if '/query/' in g['path']]
            assert len(queries) == 4
            assert len({g['path'] for g in queries}) == 4
            slots = Capacity(runtime).read()['slots']
            for segment in initial['segments']:
                operation = segment['operationId']
                assert load_job(root, operation)['status'] == 'running'
                assert slots[operation]['capacity']['state'] == 'held'
                assert slots[operation]['capacity']['reason'] != 'query_unavailable'
            path = Path(__file__).resolve().parents[1]/'.work/reports/algorithm-round-budget.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({'capacityWait': .15, 'queryDelay': 1.2, 'elapsedSeconds': elapsed,
                'historicalGets': 4, 'additionalRounds': 0, 'newPosts': 0, 'held': 4,
                'allRunningReceiptsPersisted': True, 'hardTotalDeadline': False}, indent=2), encoding='utf8')
        finally:
            await provider.http.close()


@pytest.mark.asyncio
async def test_history_zero_budget_does_not_start_get(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root, runtime = text_story(tmp_path, 5), tmp_path/'runtime'
    old = prepare(root, selected=selected('s1', 's2', 's3', 's4'))
    new = prepare(root, selected=selected('s5'))
    with FakeProvider() as fake:
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            await run_video(root, old['batchId'], provider=provider, runtime=runtime, confirm=True,
                            options=ExecutionOptions(submit_only=True))
            result = await run_video(root, new['batchId'], provider=provider, runtime=runtime, confirm=True,
                                    options=ExecutionOptions(max_polls=1, capacity_wait=0, capacity_poll=.01))
            assert result['phase'] == 'partial' and len(fake.requests) == 4 and fake.gets == []
        finally:
            await provider.http.close()


@pytest.mark.asyncio
async def test_selected_video_query_keeps_its_own_budget(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root, runtime = text_story(tmp_path, 1), tmp_path/'runtime'
    plan = prepare(root, ['ep-1'])
    with FakeProvider() as fake:
        fake.query_delays = {'1': 1.2}
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            result = await run_video(root, plan['batchId'], provider=provider, runtime=runtime, confirm=True,
                                    options=ExecutionOptions(max_polls=1, capacity_wait=.1, capacity_poll=.01))
            assert result['phase'] == 'complete' and len(fake.requests) == 1
        finally:
            await provider.http.close()
