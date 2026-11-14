import os

import pytest

from metasocli_py.domain.errors import AppError
from metasocli_py.images import workflow as iw
from metasocli_py.images.proof_cache import PreparedProofCache
from metasocli_py.providers.http import Http
from metasocli_py.providers.yiciyuang import Yiciyuang
from tests.fake_http import FakeProvider
from tests.test_image_http import image_story
from tests.test_repair_images import prepare_job


@pytest.mark.asyncio
@pytest.mark.parametrize('changed', ['plan', 'run', 'story'])
async def test_same_size_same_mtime_change_invalidates_verified_cache(tmp_path, monkeypatch, changed):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root, runtime = image_story(tmp_path, 1), tmp_path/'runtime'
    with FakeProvider() as fake:
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            plan, _ = await prepare_job(root, runtime, provider)
            cache = PreparedProofCache()
            runpath = root/f'.metasocli-py/image-runs/{plan["planId"]}.json'
            cache.plan(root, plan['planId'])
            cache.run(runpath)
            if changed == 'plan':
                file = root/f'.metasocli-py/image-plans/{plan["planId"]}.json'
                old, new = b'"n": 1', b'"n": 2'
            elif changed == 'run':
                file = runpath
                old, new = b'"maxRequests": 1', b'"maxRequests": 2'
            else:
                file = root/'metasocli-py.yaml'
                old = plan['projectId'].encode()
                new = (b'1' if old[:1] == b'0' else b'0')+old[1:]
            raw, st = file.read_bytes(), file.stat()
            assert old in raw
            changed_raw = raw.replace(old, new, 1)
            assert len(raw) == len(changed_raw)
            file.write_bytes(changed_raw)
            os.utime(file, ns=(st.st_atime_ns, st.st_mtime_ns))
            with pytest.raises(AppError):
                cache.run(runpath) if changed == 'run' else cache.plan(root, plan['planId'])
            assert fake.requests == []
        finally:
            await provider.http.close()


def test_cache_copy_isolation_and_memory_bound(tmp_path):
    from metasocli_py.persistence.codec import loads
    cache = PreparedProofCache(max_entries=2, max_bytes=30)
    for i in range(3):
        path = tmp_path/f'{i}.json'
        path.write_text('{"x":1}', encoding='utf8')
        cache._get(path, loads)
    assert len(cache.entries) == 2 and cache.total_bytes <= 30
    root = image_story(tmp_path, 1)
    plan = iw.plan_images(root, assets=['asset-0'], profile={'firstFrameSize': '1920x1088'})
    cache = PreparedProofCache()
    returned = cache.plan(root, plan['planId'])
    returned['profile']['n'] = 999
    assert cache.plan(root, plan['planId'])['profile']['n'] == 1
    assert cache.hits >= 2


@pytest.mark.asyncio
async def test_frozen_plan_change_between_admission_and_post_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root, runtime = image_story(tmp_path, 1), tmp_path/'runtime'
    plan = iw.plan_images(root, assets=['asset-0'], profile={'firstFrameSize': '1920x1088'})
    def changed(point, _job):
        if point == 'image-after-admission':
            file = root/f'.metasocli-py/image-plans/{plan["planId"]}.json'
            raw, st = file.read_bytes(), file.stat()
            file.write_bytes(raw.replace(b'"n": 1', b'"n": 2', 1))
            os.utime(file, ns=(st.st_atime_ns, st.st_mtime_ns))
    with FakeProvider() as fake:
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        try:
            with pytest.raises(AppError):
                await iw.run_images(root, plan['planId'], provider=provider, runtime=runtime, confirm=True, checkpoint=changed)
            assert fake.requests == []
        finally:
            await provider.http.close()
