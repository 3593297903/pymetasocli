import asyncio
import json
import threading
import time
from pathlib import Path

import psutil
import pytest

from metasocli_py.application.story import import_story, initialize
from metasocli_py.images.workflow import image_jobs, plan_images, run_images
from metasocli_py.providers.http import Http, ProviderError
from metasocli_py.providers.yiciyuang import Yiciyuang
from tests.fake_http import FakeProvider, png


def image_story(tmp_path, count=3):
    root = tmp_path / 'images'
    initialize(root, '合成图片')
    source = tmp_path / 'source.txt'
    source.write_text('甲', encoding='utf-8')
    recipes = [{'assetId': f'asset-{i}', 'kind': 'first_frame', 'prompt': f'完整图片提示词{i}'} for i in range(count)]
    import_story(root, {'episodeId': 'ep', 'kind': 'video-prompts', 'source': str(source),
                       'segments': [{'id': 's1', 'start': 0, 'end': 1, 'duration': 4}], 'recipes': recipes})
    return root


@pytest.mark.asyncio
async def test_200_images_real_http(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = image_story(tmp_path, 200)
    plan = plan_images(root, assets=[f'asset-{i}' for i in range(200)],
                       profile={'firstFrameSize': '1920x1088', 'maxImageBytes': 1024*1024, 'maxResponseBytes': 1024*1024})
    with FakeProvider() as fake:
        fake.image_batch_gate = 200
        fake.image_pictures = {f'完整图片提示词{i}': png(color=(i, 40, 80)) for i in range(200)}
        fake.image_delays = {f'完整图片提示词{i}': (i*73 % 200)/2000 for i in range(200)}
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'fake-image-token')
        process = psutil.Process()
        stop = threading.Event()
        samples, lags = [], []
        def sample():
            while not stop.wait(.02):
                samples.append(process.memory_info().rss)
        async def latency():
            while not stop.is_set():
                began = time.monotonic()
                await asyncio.sleep(.01)
                lags.append(max(0, time.monotonic()-began-.01)*1000)
        thread = threading.Thread(target=sample, daemon=True)
        thread.start()
        monitor = asyncio.create_task(latency())
        began = time.perf_counter()
        try:
            result = await run_images(root, plan['planId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
        finally:
            stop.set()
            thread.join(timeout=2)
            await monitor
        elapsed = time.perf_counter()-began
        assert result['complete'], result
        assert len(fake.requests) == 200
        assert {r['fields']['prompt'] for r in fake.requests} == {f'完整图片提示词{i}' for i in range(200)}
        assert len({row['operationId'] for row in result['items']}) == 200
        from metasocli_py.persistence.codec import sha256
        for row in result['items']:
            assert row['result']['sha256'] == sha256(fake.image_pictures['完整图片提示词'+row['assetId'].split('-')[1]])
        assert min(t for event, _, t in fake.events if event == 'image-response') >= max(r['time'] for r in fake.requests)
        assert result['lanes']['decode']['observedPeak'] == 2
        assert result['lanes']['registration']['observedPeak'] == 1
        report = Path(__file__).resolve().parents[1]/'.work/reports/image-200.json'
        report.parent.mkdir(parents=True, exist_ok=True)
        stamps = [r['time'] for r in fake.requests]
        report.write_text(json.dumps({'requests': len(stamps), 'firstSendMs': (min(stamps)-began)*1000,
            'lastSendMs': (max(stamps)-began)*1000, 'totalMs': elapsed*1000, 'peakRssBytes': max(samples),
            'eventLoopLagMaxMs': max(lags), 'eventLoopLagP95Ms': sorted(lags)[int(len(lags)*.95)],
            'fixture': '200 distinct synthetic 1920x1088 compressible PNGs; real loopback HTTP; no response until all 200 POST bodies received',
            'allRequestsBeforeFirstResponse': True,
            'generationConcurrencyCap': None, 'decodeLimit': 2, 'downloadLimit': 2, 'registrationLimit': 1,
            'measuredLanes': result['lanes'],
            'items': [{'assetId': j['assetId'], 'operationId': j['operationId'], 'timings': j['timings']} for j in image_jobs(root)],
            'waitReasons': ['durable intent/ledger I/O', 'response receive', 'decode semaphore', 'registration semaphore'],
            'realProviderPerformanceClaim': False}, indent=2), encoding='utf-8')
        await run_images(root, plan['planId'], provider=provider, runtime=tmp_path/'runtime', resume=True)
        assert len(fake.requests) == 200
        await provider.http.close()


@pytest.mark.asyncio
async def test_real_total_deadline(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    with FakeProvider() as fake:
        http = Http(loopback_origin=fake.origin)
        began = time.monotonic()
        with pytest.raises(ProviderError):
            await http.stream('GET', fake.origin+'/slow', tmp_path/'response.bin', total=.08, limit=1024)
        assert .06 < time.monotonic()-began < .25
        await http.close()
