import asyncio
import copy
import json
import os
import subprocess
import sys
import time

import pytest

from metasocli_py.application.assets import register_asset
from metasocli_py.application.legacy import import_content, inspect_legacy
from metasocli_py.application.story import STATE, import_story, initialize, load_story, replace_prompt
from metasocli_py.domain.errors import AppError
from metasocli_py.domain.text import utf16_length
from metasocli_py.images.workflow import image_jobs, plan_images, run_images
from metasocli_py.persistence.codec import dumps
from metasocli_py.persistence.files import atomic_write
from metasocli_py.providers.http import Http
from metasocli_py.providers.yiciyuang import Yiciyuang
from metasocli_py.video.execution import ExecutionOptions, run_video
from metasocli_py.video.planning import prepare
from tests.fake_http import FakeProvider
from tests.test_image_http import image_story
from tests.test_local_story import fixture_story, make_image


def test_cli_six_eleven_and_concurrent_replace(tmp_path):
    root = fixture_story(tmp_path)
    image = tmp_path/'a.png'
    make_image(image, 'red')
    before = load_story(root)
    def command(*args):
        return [sys.executable, '-X', 'utf8', '-m', 'metasocli_py', *args, '--root', str(root)]
    out = subprocess.run(command('assets', 'register', '--id', 'hero', '--file', str(image)), capture_output=True, timeout=20)
    assert out.returncode == 0, out.stdout
    assert load_story(root)['episodes'] == before['episodes']
    children = []
    for episode in ('ep-1', 'ep-2'):
        file = tmp_path/(episode+'.txt')
        file.write_bytes(('替换😀'+episode+'\r\n').encode())
        children.append(subprocess.Popen(command('prompts', 'replace', '--episode', episode, '--segment', 's1', '--file', str(file)), stdout=subprocess.PIPE))
    for child in children:
        stdout, _ = child.communicate(timeout=20)
        assert child.returncode == 0, stdout
    after = load_story(root)
    assert after['episodes'][2:] == before['episodes'][2:]
    assert [e['segments'][0]['prompt'] for e in after['episodes'][:2]] == ['替换😀ep-1\n', '替换😀ep-2\n']
    assert sum(len(e['segments']) for e in after['episodes']) == 11
    assert [e['segments'][0]['references'] for e in after['episodes']] == [e['segments'][0]['references'] for e in before['episodes']]
    assert len(prepare(root)['segments']) == 11


def test_utf16_narration_relocation_and_ambiguity(tmp_path):
    root = tmp_path/'voice'
    initialize(root, 'voice')
    source = tmp_path/'voice.txt'
    source.write_text('甲😀说。乙。\n', encoding='utf-8')
    import_story(root, {'episodeId': 'ep', 'kind': 'video-prompts', 'source': str(source),
        'recipes': [{'assetId': 'voice', 'kind': 'narration', 'prompt': 'test'}],
        'segments': [{'id': 's1', 'start': 0, 'end': utf16_length(source.read_text(encoding='utf-8')), 'duration': 4,
            'narration': {'assetId': 'voice', 'cues': [{'start': 0, 'end': 5}]}}]})
    source.write_text('前景。甲😀说。乙。\n', encoding='utf-8')
    replace_prompt(root, 'ep', 's1', source)
    segment = load_story(root)['episodes'][0]['segments'][0]
    assert segment['narration']['cues'] == [{'start': 3, 'end': 8}]
    before = load_story(root)
    source.write_text('甲😀说。甲😀说。\n', encoding='utf-8')
    with pytest.raises(AppError):
        replace_prompt(root, 'ep', 's1', source)
    assert load_story(root) == before


@pytest.mark.asyncio
async def test_image_dag_unlock_before_unrelated_finishes(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = image_story(tmp_path, 3)
    story = load_story(root)
    # Rebuild the synthetic draft with an actual DAG before any image plan.
    root2 = tmp_path/'dag'
    initialize(root2, 'dag')
    recipes = [a['recipe'] for a in story['assets']]
    recipes[1]['dependencies'] = ['asset-0']
    import_story(root2, {'episodeId': 'ep', 'kind': 'video-prompts', 'source': str(tmp_path/'source.txt'),
        'segments': [{'id': 's1', 'start': 0, 'end': 1, 'duration': 4}], 'recipes': recipes})
    plan = plan_images(root2, assets=['asset-0', 'asset-1', 'asset-2'], profile={'firstFrameSize': '1920x1088'})
    with FakeProvider() as fake:
        fake.image_delays['完整图片提示词2'] = 2
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        result = await run_images(root2, plan['planId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
        assert result['complete']
        dependent = next(r for r in fake.requests if r['fields']['prompt'] == '完整图片提示词1')
        unrelated_end = next(e[2] for e in fake.events if e[:2] == ('image-response', '完整图片提示词2'))
        assert dependent['time'] < unrelated_end
        assert dependent['files'][0]['bytes'] == fake.picture
        await provider.http.close()


@pytest.mark.asyncio
async def test_image_failure_keeps_sibling_receipts_and_quota(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = image_story(tmp_path, 4)
    plan = plan_images(root, assets=[f'asset-{i}' for i in range(4)], profile={'firstFrameSize': '1920x1088'})
    with FakeProvider() as fake:
        fake.image_delay = .5
        fake.fail_images.add('完整图片提示词0')
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        result = await run_images(root, plan['planId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
        assert len(fake.requests) == 4
        assert [j['status'] for j in result['items']].count('registered') == 3
        assert [j['status'] for j in result['items']].count('submit_unknown') == 1
        await provider.http.close()


@pytest.mark.asyncio
async def test_image_cancel_drains_receipts_without_resubmitting(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = image_story(tmp_path, 2)
    plan = plan_images(root, assets=['asset-0', 'asset-1'], profile={'firstFrameSize': '1920x1088'})
    with FakeProvider() as fake:
        fake.image_delay = .4
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        task = asyncio.create_task(run_images(root, plan['planId'], provider=provider, runtime=tmp_path/'runtime', confirm=True))
        while len(fake.requests) < 2:
            await asyncio.sleep(.01)
        began = time.monotonic()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert time.monotonic()-began < 6
        assert all(j['status'] == 'registered' for j in image_jobs(root))
        await run_images(root, plan['planId'], provider=provider, runtime=tmp_path/'runtime', resume=True)
        assert len(fake.requests) == 2
        await provider.http.close()


@pytest.mark.asyncio
async def test_video_partial_and_full_reuse_identity(tmp_path, monkeypatch):
    from metasocli_py.providers.metaso import Metaso
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = fixture_story(tmp_path, 1, 2)
    image = tmp_path/'a.png'
    make_image(image, 'red')
    register_asset(root, 'hero', image)
    one = prepare(root, selected={'schemaVersion': 1, 'episodes': [{'episodeId': 'ep-1', 'segmentIds': ['s1']}]})
    both = prepare(root)
    with FakeProvider() as fake:
        provider = Metaso(Http(loopback_origin=fake.origin), 'synthetic')
        options = ExecutionOptions(max_polls=1, poll_seconds=0, capacity_poll=.01)
        first = await run_video(root, one['batchId'], provider=provider, runtime=tmp_path/'runtime', confirm=True, options=options)
        assert not first['reused'] and not first['segments'][0]['reused']
        mixed = await run_video(root, both['batchId'], provider=provider, runtime=tmp_path/'runtime', confirm=True, options=options)
        assert [r['reused'] for r in mixed['segments']] == [True, False]
        final = await run_video(root, both['batchId'], provider=provider, runtime=tmp_path/'runtime', confirm=True, options=options)
        assert final['reused'] and len(fake.requests) == 2
        await provider.http.close()


def test_static_legacy_content_only_and_unknown_rejection(tmp_path):
    import shutil
    root = fixture_story(tmp_path, 1, 1)
    file = tmp_path/'a.png'
    make_image(file, 'red')
    register_asset(root, 'hero', file)
    legacy = tmp_path/'legacy'
    shutil.copytree(root, legacy)
    story = copy.deepcopy(load_story(root))
    story['owner'] = 'metasocli'
    story.pop('hashVersion')
    for episode in story['episodes']:
        episode.pop('offsetEncoding')
        for field in ('rawPath', 'textPath'):
            episode['source'][field] = episode['source'][field].replace(STATE, '.metasocli')
    os.rename(legacy/STATE, legacy/'.metasocli')
    (legacy/'metasocli-py.yaml').unlink()
    # Legacy uses removable PID locks, not Python's retained OS lock files.
    for lock in (legacy/'.metasocli').rglob('*.lock'):
        lock.unlink()
    atomic_write(legacy/'metasocli.yaml', dumps(story))
    baseline = inspect_legacy(legacy)
    assert baseline['eligible']
    target = tmp_path/'imported'
    result = import_content(legacy, target, 'content only')
    assert result['projectId'] != story['projectId'] and not result['tasksImported']
    assert inspect_legacy(legacy) == baseline
    assert load_story(target)['assets'][0]['media']['sha256'] == story['assets'][0]['media']['sha256']
    atomic_write(legacy/'.metasocli/jobs/unknown.json', json.dumps({'status': 'submit_unknown'}).encode())
    assert not inspect_legacy(legacy)['eligible']
    with pytest.raises(AppError) as caught:
        import_content(legacy, tmp_path/'blocked', 'blocked')
    assert caught.value.code == 'LEGACY_ACTIVE'
