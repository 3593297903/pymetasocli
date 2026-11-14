import copy
import json
import time
from pathlib import Path

import pytest

from metasocli_py.application.story import import_story, initialize
from metasocli_py.domain.text import utf16_length
from metasocli_py.providers.http import Http
from metasocli_py.providers.metaso import Metaso
from metasocli_py.video.capacity import apply_decision
from metasocli_py.video.execution import ExecutionOptions, run_video
from metasocli_py.video.planning import prepare
from metasocli_py.video.retry import authorize_retry
from tests.fake_http import FakeProvider


def text_story(tmp_path, count=8, name='story'):
    root = tmp_path / name
    initialize(root, '合成视频')
    texts = [f'镜头{i}，甲😀乙。\n' for i in range(count)]
    source = tmp_path / (name + '.txt')
    source.write_text(''.join(texts), encoding='utf-8')
    segments, offset = [], 0
    for index, text in enumerate(texts):
        segments.append({'id': f's{index+1}', 'start': offset, 'end': offset+utf16_length(text), 'duration': 4})
        offset += utf16_length(text)
    import_story(root, {'episodeId': 'ep-1', 'kind': 'video-prompts', 'source': str(source), 'segments': segments})
    return root


@pytest.mark.asyncio
async def test_eight_segments_refill_before_slow_download(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = text_story(tmp_path)
    preparing = time.perf_counter()
    plan = prepare(root, ['ep-1'])
    prepare_ms = (time.perf_counter()-preparing)*1000
    with FakeProvider() as fake:
        fake.download_delay = .5
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic-token')
        result = await run_video(root, plan['batchId'], provider=provider, runtime=tmp_path/'runtime', confirm=True,
                                 options=ExecutionOptions(max_polls=2, poll_seconds=.01, capacity_poll=.01))
        assert result['phase'] == 'complete', result
        assert not result['reused']
        assert not any(s['reused'] for s in result['segments'])
        assert len(fake.tasks) == 8
        assert fake.max_creates == 4
        assert fake.max_live <= 4
        create5 = next(t for e, i, t in fake.events if e == 'create' and i == '5')
        assert create5 < min(t for e, i, t in fake.events if e == 'download')
        assert sorted(r['fields']['content'][0]['text'] for r in fake.requests) == sorted(s['segment']['prompt'] for s in plan['segments'])
        from metasocli_py.video.store import load_job
        sends = [load_job(root, s['operationId'])['timings']['send'] for s in result['segments']]
        assert sends == sorted(sends)
        assert all(r['fields']['context_ir_enabled'] is True for r in fake.requests)
        report = Path(__file__).resolve().parents[1]/'.work/reports/video-eight.json'
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({'items': [load_job(root, s['operationId'])['timings'] for s in result['segments']],
            'serverEvents': fake.events, 'maxCreates': fake.max_creates, 'maxLive': fake.max_live,
            'fifthCreateBeforeFirstDownload': True, 'syntheticCreateDelaySeconds': fake.create_delay,
            'syntheticDownloadDelaySeconds': fake.download_delay, 'prepareMs': prepare_ms,
            'deliveryMs': result['timings']['deliveryMs'], 'totalMs': result['timings']['executeMs']}, indent=2), encoding='utf-8')
        again = await run_video(root, plan['batchId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
        assert again['reused'] and len(fake.tasks) == 8
        await provider.http.close()


@pytest.mark.asyncio
async def test_unknown_no_resubmit_and_exact_one_retry(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = text_story(tmp_path, count=1)
    plan = prepare(root, ['ep-1'])
    with FakeProvider() as fake:
        fake.fail_video = True
        provider = Metaso(Http(loopback_origin=fake.origin), 'fake-token')
        result = await run_video(root, plan['batchId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
        operation = result['segments'][0]['operationId']
        assert result['segments'][0]['status'] == 'submit_unknown'
        assert result['capacity'][operation]['state'] == 'released'
        await run_video(root, plan['batchId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
        assert len(fake.tasks) == 1
        auth = authorize_retry(root, plan['batchId'], operation, True, True)
        assert authorize_retry(root, plan['batchId'], operation, True, True) == auth
        fake.fail_video = False
        result = await run_video(root, plan['batchId'], provider=provider, runtime=tmp_path/'runtime', resume=True)
        assert result['phase'] == 'complete', result
        assert len(fake.tasks) == 2
        await provider.http.close()


def test_r3_terminal_late_active_and_watermarks():
    slot = {'operationId': 'op', 'projectId': 'project', 'requestHash': 'hash',
            'capacity': {'version': 0, 'issued': 3, 'applied': 0, 'state': 'held', 'terminal': False}}
    event = {'operationId': 'op', 'projectId': 'project', 'requestHash': 'hash', 'taskId': '1'}
    assert apply_decision(slot, {**event, 'sequence': 3, 'reason': 'query_unavailable'})
    assert slot['capacity']['state'] == 'released'
    assert not apply_decision(slot, {**event, 'sequence': 2, 'reason': 'remote_active_recovered'})
    slot['capacity']['issued'] = 4
    assert apply_decision(slot, {**event, 'sequence': 4, 'reason': 'remote_active_recovered'})
    assert 'lastRestore' in slot['capacity']
    assert apply_decision(slot, {**event, 'sequence': 1, 'reason': 'provider_terminal'})
    before = copy.deepcopy(slot)
    assert not apply_decision(slot, {**event, 'sequence': 10, 'reason': 'remote_active_recovered'})
    assert slot == before
