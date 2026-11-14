from pathlib import Path

import pytest

from metasocli_py.application.assets import register_asset
from metasocli_py.application.story import import_story, initialize
from metasocli_py.images.collection import collect_preparation
from metasocli_py.images.workflow import image_jobs, plan_images, prepare_images, run_images
from metasocli_py.persistence.codec import sha256
from metasocli_py.persistence.files import write_json
from metasocli_py.providers.http import Http
from metasocli_py.providers.yiciyuang import Yiciyuang
from tests.fake_http import FakeProvider, png
from tests.test_image_http import image_story

PROFILE = {'firstFrameSize': '1920x1088', 'maxImageBytes': 1024*1024, 'maxResponseBytes': 1024*1024}


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [401, 429, 500, 503])
async def test_image_status_no_automatic_post_retry(tmp_path, monkeypatch, status):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = image_story(tmp_path, 1)
    plan = plan_images(root, assets=['asset-0'], profile=PROFILE)
    with FakeProvider() as fake:
        fake.status_code = status
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        for confirm in (True, False):
            result = await run_images(root, plan['planId'], provider=provider, runtime=tmp_path/'runtime', confirm=confirm, resume=not confirm)
            assert result['items'][0]['status'] == ('rejected' if status in (401, 429) else 'submit_unknown')
        assert len(fake.requests) == 1
        await provider.http.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('truncate', [False, True])
async def test_image_download_or_truncation_never_regenerates(tmp_path, monkeypatch, truncate):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = image_story(tmp_path, 1)
    plan = plan_images(root, assets=['asset-0'], profile=PROFILE)
    with FakeProvider() as fake:
        fake.truncate = truncate
        fake.image_url = True
        fake.fail_download = True
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        await run_images(root, plan['planId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
        fake.fail_download = fake.truncate = False
        result = await run_images(root, plan['planId'], provider=provider, runtime=tmp_path/'runtime', resume=True)
        assert len(fake.requests) == 1
        assert result['complete'] is (not truncate)
        assert all('Authorization' not in r['headers'] for r in fake.gets)
        await provider.http.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('references', [1, 2])
async def test_actual_multipart_order_bytes_names_mime(tmp_path, monkeypatch, references):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = tmp_path/'story'
    initialize(root, 'DAG')
    source = tmp_path/'source.txt'
    source.write_text('甲', encoding='utf-8')
    recipes = [{'assetId': 'a', 'kind': 'first_frame', 'prompt': 'a'},
               {'assetId': 'b', 'kind': 'first_frame', 'prompt': 'b'},
               {'assetId': 'c', 'kind': 'first_frame', 'prompt': 'c', 'dependencies': ['a', 'b'][:references]}]
    import_story(root, {'episodeId': 'ep', 'kind': 'video-prompts', 'source': str(source),
                       'segments': [{'id': 's1', 'start': 0, 'end': 1, 'duration': 4}], 'recipes': recipes})
    expected = []
    for index, asset in enumerate(['a', 'b'][:references]):
        data = png(color=(index+1, 3, 4))
        file = tmp_path/f'{asset}.png'
        file.write_bytes(data)
        register_asset(root, asset, file)
        expected.append(data)
    plan = plan_images(root, assets=['c'], profile=PROFILE)
    with FakeProvider() as fake:
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        result = await run_images(root, plan['planId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
        assert result['complete']
        request = fake.requests[0]
        assert request['path'] == '/v1/images/edits'
        assert [f['bytes'] for f in request['files']] == expected
        assert [f['field'] for f in request['files']] == ['image' if references == 1 else 'image[]']*references
        assert all(f['mime'] == 'image/png' and f['filename'].endswith('.png') for f in request['files'])
        await provider.http.close()


@pytest.mark.asyncio
async def test_preparation_full_handoff_and_collect(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    root = tmp_path/'story'
    story = initialize(root, 'prepared')
    (root/'source.txt').write_text('甲', encoding='utf-8')
    prompt = '首帧完整具体内容'
    draft = {'episodeId': 'ep', 'kind': 'video-prompts', 'source': 'source.txt',
             'segments': [{'id': 's1', 'start': 0, 'end': 1, 'duration': 4, 'references': [{'assetId': 'a', 'role': 'first_frame'}]}],
             'recipes': [{'assetId': 'a', 'kind': 'first_frame', 'prompt': prompt, 'dependencies': [], 'exactText': []}]}
    request = {'schemaVersion': '1.0.0', 'episodeId': 'ep', 'modelPreference': None, 'requireExactModel': False,
        'assets': [{'assetId': 'a', 'version': 'v1', 'order': 1, 'kind': 'first_frame', 'name': '首帧', 'required': True,
            'requiredBySegments': ['s1'], 'visualDescription': '完整外观', 'sourceFacts': ['原文事实'],
            'continuityRequirements': [], 'exclude': [], 'dependencyAssetIds': [], 'exactText': []}]}
    recipe = {'schemaVersion': '1.0.0', 'episodeId': 'ep', 'assets': [{'assetId': 'a', 'kind': 'first_frame', 'status': 'planned',
        'generationPrompt': prompt, 'recipeSha256': sha256(prompt), 'existingRelativePath': None, 'contentSha256': None, 'reason': None}]}
    for name, value in [('draft', draft), ('request', request), ('recipe', recipe), ('profile', PROFILE)]:
        write_json(root/f'{name}.json', value)
    batch = {'schemaVersion': 1, 'projectId': story['projectId'], 'entries': [{'episodeId': 'ep', 'draftPath': 'draft.json',
             'requestPath': 'request.json', 'recipePath': 'recipe.json', 'replace': False}], 'scope': {'episodes': ['ep']}, 'profilePath': 'profile.json'}
    prepared = prepare_images(root, batch)
    assert prepare_images(root, preparation=prepared['preparationId']) == prepared
    with FakeProvider() as fake:
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        await run_images(root, prepared['planId'], provider=provider, runtime=tmp_path/'runtime', confirm=True)
        result = collect_preparation(root, prepared['preparationId'])
        assert result['complete']
        assert Path(result['episodes'][0]['resultPath']).is_file()
        assert len(fake.requests) == 1
        await provider.http.close()


@pytest.mark.asyncio
async def test_other_story_unknown_does_not_block_images(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    for name in ('a', 'b'):
        (tmp_path/name).mkdir()
    a, b = image_story(tmp_path/'a', 1), image_story(tmp_path/'b', 1)
    runtime = tmp_path/'runtime'
    with FakeProvider() as fake:
        provider = Yiciyuang(Http(loopback_origin=fake.origin), 'synthetic')
        fake.status_code = 502
        pa = plan_images(a, assets=['asset-0'], profile=PROFILE)
        await run_images(a, pa['planId'], provider=provider, runtime=runtime, confirm=True)
        fake.status_code = 200
        pb = plan_images(b, assets=['asset-0'], profile=PROFILE)
        assert (await run_images(b, pb['planId'], provider=provider, runtime=runtime, confirm=True))['complete']
        assert image_jobs(a)[0]['status'] == 'submit_unknown'
        await provider.http.close()
