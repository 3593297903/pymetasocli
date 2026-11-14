import copy
import uuid
from pathlib import Path

from ..contracts.story import ImportDraft, Manifest, Parameters, parse
from ..domain.errors import AppError
from ..domain.text import (
    coverage,
    duration,
    normalize_text,
    render_prompt,
    utf16_length,
    utf16_slice,
    validate_narration,
)
from ..persistence.codec import HASH_VERSION, digest, dumps, loads, sha256
from ..persistence.files import (
    lock,
    project_path,
    read_stable,
    recover_transactions,
    safe_path,
    transaction,
    write_json,
)

MANIFEST = 'metasocli-py.yaml'
STATE = '.metasocli-py'


def load_story(root: Path | str) -> dict:
    root = safe_path(root)
    file = project_path(root, MANIFEST)
    if not file.exists():
        raise AppError('NOT_INITIALIZED', 'No metasocli-py.yaml at the explicit story root.')
    return validate_story_bytes(read_stable(file))


def validate_story_bytes(raw: bytes) -> dict:
    story = parse(Manifest, loads(raw, yaml_input=True))
    for field, key in [('episodes', 'id'), ('assets', 'recipe')]:
        ids = [item[key]['assetId'] if key == 'recipe' else item[key] for item in story[field]]
        if len(ids) != len(set(ids)):
            raise AppError('INVALID_MANIFEST', 'Identifiers must be unique.')
    for asset in story['assets']:
        if digest(asset['recipe']) != asset['recipeHash']:
            raise AppError('CONTENT_CHANGED', 'Recipe hash mismatch.')
    return story


def initialize(root: Path | str, name: str) -> dict:
    root = safe_path(root)
    # No old engine/source/story roots, including their children.
    for parent in [root, *root.parents]:
        if (parent / 'metasocli.yaml').exists() or (parent / 'story2libtv.yaml').exists():
            raise AppError('LEGACY_ROOT', 'Initialize a new independent story directory.')
        package = parent / 'package.json'
        if package.exists():
            data = loads(read_stable(package))
            if data.get('name') in ('metasocli', 'story-to-libtv'):
                raise AppError('LEGACY_ROOT', 'Old source directories are read-only.')
    if (root / MANIFEST).exists():
        return load_story(root)
    if root.exists() and any(root.iterdir()):
        raise AppError('ROOT_NOT_EMPTY', 'Initialize an empty dedicated directory.')
    root.mkdir(parents=True, exist_ok=True)
    project_path(root, STATE).mkdir()
    story = {'schemaVersion': 1, 'owner': 'metasocli-py', 'hashVersion': HASH_VERSION,
             'projectId': str(uuid.uuid4()), 'name': name, 'revision': 0, 'episodes': [], 'assets': []}
    parse(Manifest, story)
    write_json(root / MANIFEST, story)
    return story


def validate_graph(assets: list[dict]) -> None:
    by_id = {a['recipe']['assetId']: a['recipe'] for a in assets}
    visited: set[str] = set()
    active: set[str] = set()

    def visit(asset_id: str) -> None:
        if asset_id in active or asset_id not in by_id:
            raise AppError('RECIPE_DEPENDENCY', 'Missing or cyclic recipe dependency.')
        if asset_id in visited:
            return
        active.add(asset_id)
        recipe = by_id[asset_id]
        deps = recipe['dependencies']
        if len(deps) != len(set(deps)) or (recipe['kind'] == 'narration' and (deps or recipe['exactText'])):
            raise AppError('RECIPE_DEPENDENCY', 'Invalid recipe dependencies.')
        for dependency in deps:
            if by_id.get(dependency, {}).get('kind') == 'narration':
                raise AppError('RECIPE_DEPENDENCY', 'Images cannot depend on audio.')
            visit(dependency)
        active.remove(asset_id)
        visited.add(asset_id)

    for asset_id in by_id:
        visit(asset_id)


def bindings(story: dict, segment: dict) -> None:
    assets = {a['recipe']['assetId']: a for a in story['assets']}
    refs = segment['references']
    if len({r['assetId'] for r in refs}) != len(refs):
        raise AppError('DUPLICATE_REFERENCE', 'Repeated reference.')
    for ref in refs:
        recipe = assets.get(ref['assetId'], {}).get('recipe')
        if recipe is None:
            raise AppError('MISSING_RECIPE', 'Reference recipe missing.')
        if recipe['kind'] == 'narration' or (recipe['kind'] == 'first_frame') != (ref['role'] == 'first_frame'):
            raise AppError('ASSET_ROLE', 'Reference role mismatch.')
    if any(r['role'] == 'first_frame' for r in refs) and len(refs) != 1:
        raise AppError('H3_MODE', 'First frame must be the only image.')
    voice = segment.get('narration')
    if voice and assets.get(voice['assetId'], {}).get('recipe', {}).get('kind') != 'narration':
        raise AppError('MISSING_RECIPE', 'Narration recipe missing.')
    validate_narration(segment)


def normalize_import(value: dict, raw: bytes | None = None) -> tuple[dict, bytes, str, dict]:
    draft = parse(ImportDraft, value)
    raw = read_stable(safe_path(draft['source'])) if raw is None else raw
    text = normalize_text(raw)
    coverage(text, draft['segments'])
    segments = []
    for item in draft['segments']:
        original = utf16_slice(text, item['start'], item['end'])
        prompt = normalize_text(item.get('prompt') if item.get('prompt') is not None else original)
        if draft['kind'] == 'video-prompts' and prompt != original:
            raise AppError('PROMPT_CHANGED', 'Finished prompt must match the complete source span.')
        if draft['kind'] == 'script' and original not in prompt:
            raise AppError('DIALOGUE_CHANGED', 'Script prompt must retain its full source span.')
        item = {**item, **duration(item['duration']), 'references': item.get('references', []),
                'parameters': Parameters.model_validate(item.get('parameters', {})).model_dump(),
                'prompt': prompt, 'promptHash': sha256(prompt)}
        validate_narration(item)
        segments.append(item)
    raw_hash, text_hash = sha256(raw), sha256(text)
    source = {'origin': Path(draft['source']).name, 'rawPath': f'{STATE}/sources/{raw_hash}.bin',
              'rawHash': raw_hash, 'textPath': f'{STATE}/sources/{text_hash}.txt', 'textHash': text_hash}
    episode = {'id': draft['episodeId'], 'kind': draft['kind'], 'offsetEncoding': 'utf16',
               'source': source, 'segments': segments}
    return draft, raw, text, episode


def merge_import(story: dict, draft: dict, episode: dict, replace: bool) -> dict:
    story = copy.deepcopy(story)
    previous = next((e for e in story['episodes'] if e['id'] == episode['id']), None)
    if previous and previous != episode and not replace:
        raise AppError('EPISODE_EXISTS', 'Different episode already exists; explicit replacement required.')
    for recipe in draft.get('recipes', []):
        recipe = {'exactText': [], 'dependencies': [], **recipe}
        from ..resources import append_denoise
        recipe['prompt'] = append_denoise(recipe['kind'], recipe['prompt'])
        old = next((a for a in story['assets'] if a['recipe']['assetId'] == recipe['assetId']), None)
        if old and old['recipeHash'] != digest(recipe):
            raise AppError('RECIPE_CONFLICT', 'Changed recipe requires a new asset ID.')
        if old is None:
            story['assets'].append({'recipe': recipe, 'recipeHash': digest(recipe), 'media': None})
    validate_graph(story['assets'])
    for segment in episode['segments']:
        bindings(story, segment)
    story['episodes'] = [episode if e['id'] == episode['id'] else e for e in story['episodes']]
    if previous is None:
        story['episodes'].append(episode)
    parse(Manifest, story)
    return story


def import_story(root: Path, value: dict, replace: bool = False, expected_episode: str | None = None,
                 enforce_previous: bool = False) -> dict:
    draft, raw, text, episode = normalize_import(value)
    source = episode['source']
    with lock(project_path(root, f'{STATE}/story.lock')):
        recover_transactions(root)
        story = load_story(root)
        previous = next((e for e in story['episodes'] if e['id'] == episode['id']), None)
        if enforce_previous and (digest(previous) if previous else None) not in (expected_episode, digest(episode)):
            raise AppError('IMAGE_PREPARATION_STALE', 'Episode was edited after preparation capture.')
        updated = merge_import(story, draft, episode, replace)
        if previous == episode and all((root / source[k]).exists() for k in ('rawPath', 'textPath')):
            if updated == story:
                return story
        story = updated
        story['revision'] += 1
        parse(Manifest, story)
        transaction(root, {source['rawPath']: raw, source['textPath']: text.encode('utf-8'), MANIFEST: dumps(story)}, MANIFEST)
        return story


def target(story: dict, episode_id: str, segment_id: str) -> tuple[dict, dict]:
    episode = next((e for e in story['episodes'] if e['id'] == episode_id), None)
    if episode is None:
        raise AppError('EPISODE_MISSING', 'Episode does not exist.')
    segment = next((s for s in episode['segments'] if s['id'] == segment_id), None)
    if segment is None:
        raise AppError('SEGMENT_MISSING', 'Segment does not exist.')
    return episode, segment


def replace_prompt(root: Path, episode_id: str, segment_id: str, file: Path,
                   expected_sha256: str | None = None, expected_prompt_hash: str | None = None,
                   explicit_cues: dict | None = None) -> dict:
    raw = read_stable(file)
    prompt = normalize_text(raw)
    if expected_sha256 and sha256(raw) != expected_sha256:
        raise AppError('CONTENT_CHANGED', 'Selected input SHA-256 mismatch.')
    baseline = load_story(root)
    old_episode, captured = target(baseline, episode_id, segment_id)
    if old_episode['kind'] != 'video-prompts':
        raise AppError('PROMPT_REPLACEMENT_KIND', 'Replacement supports finished prompts only.')
    desired = copy.deepcopy(captured)
    voice = desired.get('narration')
    mode = 'kept' if voice else 'none'
    if explicit_cues is not None:
        if not voice or explicit_cues.get('promptHash') != sha256(prompt):
            raise AppError('NARRATION_REMAP_REQUIRED', 'Explicit narration mapping identity mismatch.')
        cues = explicit_cues['cues']
        if any(utf16_slice(prompt, c['start'], c['end']) != c['text'] for c in cues):
            raise AppError('NARRATION_REMAP_REQUIRED', 'Explicit cue text mismatch.')
        voice['cues'] = [{'start': c['start'], 'end': c['end']} for c in cues]
        mode = 'explicit'
    elif voice and prompt != captured['prompt']:
        cues, cursor = [], 0
        for cue in voice['cues']:
            quote = utf16_slice(captured['prompt'], cue['start'], cue['end'])
            start = prompt.find(quote)
            if start < cursor or prompt.find(quote, start + 1) != -1:
                raise AppError('NARRATION_REMAP_REQUIRED', 'Narration text is missing, ambiguous or reordered.')
            end = start + len(quote)
            cues.append({'start': utf16_length(prompt[:start]), 'end': utf16_length(prompt[:end])})
            cursor = end
        voice['cues'] = cues
        mode = 'relocated'
    desired.update(prompt=prompt, promptHash=sha256(prompt))
    render_prompt(desired)
    with lock(project_path(root, f'{STATE}/story.lock')):
        recover_transactions(root)
        story = load_story(root)
        episode, current = target(story, episode_id, segment_id)
        def fingerprint(s):
            return digest({k: v for k, v in s.items() if k not in ('start', 'end')})
        unchanged = fingerprint(current) == fingerprint(desired)
        if story['projectId'] != baseline['projectId'] or (not unchanged and (fingerprint(current) != fingerprint(captured)
                or (expected_prompt_hash and current['promptHash'] != expected_prompt_hash))):
            raise AppError('PROMPT_REPLACEMENT_STALE', 'Concurrent edit changed the selected segment.')
        src = episode['source']
        old_raw = read_stable(project_path(root, src['rawPath']))
        old_text = read_stable(project_path(root, src['textPath']))
        text = normalize_text(old_raw)
        if sha256(old_raw) != src['rawHash'] or sha256(old_text) != src['textHash'] or text.encode('utf-8') != old_text:
            raise AppError('SOURCE_CHANGED', 'Source snapshots are damaged.')
        coverage(text, episode['segments'])
        if any(utf16_slice(text, s['start'], s['end']) != s['prompt'] or sha256(s['prompt']) != s['promptHash'] for s in episode['segments']):
            raise AppError('SOURCE_CHANGED', 'Prompt differs from source span.')
        bindings(story, desired)
        revision = story['revision']
        if not unchanged:
            new_text = utf16_slice(text, 0, current['start']) + prompt + utf16_slice(text, current['end'], utf16_length(text))
            delta = utf16_length(prompt) - utf16_length(current['prompt'])
            index = episode['segments'].index(current)
            desired.update(start=current['start'], end=current['start'] + utf16_length(prompt))
            episode['segments'][index] = desired
            for segment in episode['segments'][index+1:]:
                segment['start'] += delta
                segment['end'] += delta
            h = sha256(new_text)
            episode['source'] = {'origin': f'prompt-replacement:{episode_id}/{segment_id}',
                'rawPath': f'{STATE}/sources/{h}.bin', 'rawHash': h,
                'textPath': f'{STATE}/sources/{h}.txt', 'textHash': h}
            story['revision'] += 1
            parse(Manifest, story)
            data = new_text.encode('utf-8')
            transaction(root, {episode['source']['rawPath']: data, episode['source']['textPath']: data,
                f'{STATE}/prompt-replacements/inputs/{sha256(raw)}.bin': raw, MANIFEST: dumps(story)}, MANIFEST)
        return {'schemaVersion': 1, 'state': 'unchanged' if unchanged else 'replaced', 'changed': not unchanged,
                'projectId': story['projectId'], 'episodeId': episode_id, 'segmentId': segment_id,
                'previousPromptHash': current['promptHash'], 'promptHash': sha256(prompt), 'inputSha256': sha256(raw),
                'previousRevision': revision, 'revision': story['revision'], 'narrationMode': mode}
