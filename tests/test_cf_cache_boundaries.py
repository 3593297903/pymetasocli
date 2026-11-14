"""Acceptance boundaries for exact-byte cache and quota-triggered repair."""
from pathlib import Path

import pytest

from metasocli_py.domain.errors import AppError
from metasocli_py.images import workflow as iw
from metasocli_py.images.proof_cache import PreparedProofCache
from metasocli_py.persistence.codec import loads
from metasocli_py.persistence.files import lock
from metasocli_py.providers.http import Http
from metasocli_py.providers.yiciyuang import Yiciyuang
from tests.fake_http import FakeProvider
from tests.test_image_http import image_story
from tests.test_repair_images import prepare_job


@pytest.mark.parametrize('limits', [(2, 100), (4, 14)])
def test_lru_recency_and_raw_byte_eviction(tmp_path, limits):
    cache = PreparedProofCache(max_entries=limits[0], max_bytes=limits[1])
    files = [tmp_path/f'{i}.json' for i in range(3)]
    calls = []

    def validate(raw):
        calls.append(raw)
        return loads(raw)

    for i, file in enumerate(files):
        file.write_text('{"v":'+str(i)+'}', encoding='utf-8')
    for i in (0, 1, 0, 2):
        assert cache._get(files[i], validate) == {'v': i}
    assert list(cache.entries) == [str(files[0]), str(files[2])]
    assert cache.total_bytes == 14
    assert len(calls) == 3
    cache._get(files[1], validate)
    assert len(calls) == 4


def test_oversize_is_validated_each_time_without_displacing_small_entry(tmp_path):
    cache = PreparedProofCache(max_entries=4, max_bytes=7)
    small, large = tmp_path/'small', tmp_path/'large'
    small.write_bytes(b'{"v":0}')
    large.write_bytes(b'{"v":100}')
    calls = []

    def validate(raw):
        calls.append(raw)
        return loads(raw)

    cache._get(small, validate)
    for _ in range(2):
        assert cache._get(large, validate) == {'v': 100}
    assert list(cache.entries) == [str(small)]
    assert cache.total_bytes == 7 and len(calls) == 3


def test_missing_file_cannot_fall_back_to_verified_bytes(tmp_path):
    file = tmp_path/'record'
    file.write_bytes(b'{"v":0}')
    cache = PreparedProofCache()
    cache._get(file, loads)
    file.unlink()
    with pytest.raises((AppError, OSError)):
        cache._get(file, loads)
    assert cache.hits == 0


@pytest.mark.asyncio
async def test_run_copy_and_quota_errors_do_not_trigger_repair(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root, runtime = image_story(tmp_path, 1), tmp_path/'runtime'

    def forbidden_scan(*_args):
        pytest.fail('Only quota obstruction may trigger a repair scan')

    with FakeProvider() as fake:
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            plan, job = await prepare_job(root, runtime, provider)
            quota = iw.Quota(runtime, plan['profile'], root)
            monkeypatch.setattr(quota, 'repair_prepared', forbidden_scan)
            runpath = root/f'.metasocli-py/image-runs/{plan["planId"]}.json'
            returned = quota.proof_cache.run(runpath)
            returned['items'].clear()
            assert quota.proof_cache.run(runpath)['items'] == {'asset-0': job['operationId']}
            with lock(Path(quota.owner)):
                assert quota.update(job, reserve=True)
                assert quota.update(job, reserve=True)
                assert quota.update(job)
                ledger = quota.folder/'ledger.json'
                ledger.write_bytes(b'{"corrupt":true}')
                with pytest.raises(AppError):
                    quota.update(job, reserve=True)
            assert fake.requests == []
        finally:
            await provider.http.close()


@pytest.mark.asyncio
async def test_successful_admission_and_status_updates_never_scan_old_sources(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root, runtime = image_story(tmp_path, 2), tmp_path/'runtime'
    plan = iw.plan_images(root, assets=['asset-0', 'asset-1'], profile={'firstFrameSize': '1920x1088'})

    def forbidden_scan(*_args):
        pytest.fail('Unblocked run must not scan old sources')

    monkeypatch.setattr(iw.Quota, 'repair_prepared', forbidden_scan)
    with FakeProvider() as fake:
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            result = await iw.run_images(root, plan['planId'], provider=provider, runtime=runtime, confirm=True)
            assert result['complete'] and len(fake.requests) == 2
            await iw.run_images(root, plan['planId'], provider=provider, runtime=runtime, resume=True)
            assert len(fake.requests) == 2
        finally:
            await provider.http.close()
