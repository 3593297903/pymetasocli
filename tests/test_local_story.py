import copy

import pytest
from PIL import Image

from metasocli_py.application.assets import register_asset
from metasocli_py.application.story import import_story, initialize, load_story, replace_prompt
from metasocli_py.domain.errors import AppError
from metasocli_py.domain.text import utf16_length
from metasocli_py.video.planning import prepare


def fixture_story(tmp_path, episodes=6, segments=11):
    root = tmp_path / 'story'
    initialize(root, '合成测试')
    for episode in range(episodes):
        count = 2 if episode < segments - episodes else 1
        prompts = [f'第{episode}集第{s}段：甲😀乙。\n' for s in range(count)]
        source = tmp_path / f'source{episode}.txt'
        source.write_text(''.join(prompts), encoding='utf-8')
        cursor, items = 0, []
        for index, text in enumerate(prompts):
            items.append({'id': f's{index+1}', 'start': cursor, 'end': cursor+utf16_length(text), 'duration': 6.666,
                          'references': [{'assetId': 'hero', 'role': 'reference_image'}]})
            cursor += utf16_length(text)
        import_story(root, {'episodeId': f'ep-{episode+1}', 'kind': 'video-prompts', 'source': str(source),
                           'offsetEncoding': 'utf16', 'segments': items,
                           'recipes': [{'assetId': 'hero', 'kind': 'character', 'prompt': '合成人物完整配方'}]})
    return root


def make_image(path, color):
    image = Image.new('RGB', (256, 256), color)
    image.save(path)


def test_six_episodes_eleven_segments_replace(tmp_path, monkeypatch):
    root = fixture_story(tmp_path)
    image = tmp_path / 'image.png'
    make_image(image, 'red')
    register_asset(root, 'hero', image)
    before = load_story(root)
    assert sum(len(e['segments']) for e in before['episodes']) == 11
    plan1 = prepare(root, ['ep-1'])
    make_image(image, 'blue')
    register_asset(root, 'hero', image)
    after = load_story(root)
    assert after['episodes'] == before['episodes']
    assert after['assets'][0]['recipe'] == before['assets'][0]['recipe']
    plan2 = prepare(root, ['ep-1'])
    assert plan2['segments'][0]['requestHash'] != plan1['segments'][0]['requestHash']
    old = copy.deepcopy(after)
    prompt = tmp_path / 'new.txt'
    prompt.write_bytes('\ufeff全新😀稿件\r\n'.encode('utf-8'))
    import metasocli_py.application.story as module
    original = module.read_stable
    def guarded(path, *args, **kwargs):
        assert 'assets' not in str(path) and 'runtime' not in str(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(module, 'read_stable', guarded)
    receipt = replace_prompt(root, 'ep-1', 's1', prompt)
    assert receipt['changed']
    new = load_story(root)
    assert new['assets'] == old['assets']
    assert new['episodes'][1:] == old['episodes'][1:]
    a, b = old['episodes'][0]['segments'], new['episodes'][0]['segments']
    assert b[0]['prompt'] == '全新😀稿件\n'
    assert b[0]['duration'] == a[0]['duration'] == 7
    assert b[0]['targetDurationSeconds'] == 6.666
    assert b[1]['prompt'] == a[1]['prompt']
    assert b[1]['start'] == b[0]['end']
    assert not replace_prompt(root, 'ep-1', 's1', prompt)['changed']


def test_invalid_duration_bool_and_string(tmp_path):
    root = tmp_path / 'story'
    initialize(root, '测试')
    file = tmp_path / 'source.txt'
    file.write_text('甲', encoding='utf-8')
    for duration in (True, '12'):
        with pytest.raises(AppError):
            import_story(root, {'episodeId': 'ep', 'kind': 'video-prompts', 'source': str(file),
                               'segments': [{'id': 's1', 'start': 0, 'end': 1, 'duration': duration}]})
