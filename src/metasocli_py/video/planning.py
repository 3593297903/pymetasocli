import base64
import copy
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from ..application.story import STATE, bindings, load_story, target
from ..domain.errors import AppError
from ..domain.text import coverage, normalize_text, render_prompt, utf16_slice
from ..media.inspect import MAX_AUDIO, MAX_IMAGE, audio_info, image_info
from ..persistence.codec import digest, sealed, sha256, verify
from ..persistence.files import atomic_write, lock, project_path, read_json, read_stable, write_json


def now() -> str:
    return datetime.now(UTC).isoformat().replace('+00:00', 'Z')


def selection(story: dict, episodes: list[str] | None = None, selected: dict | None = None) -> list[tuple[str, str]]:
    if selected is not None:
        if set(selected) - {'schemaVersion', 'episodes'} or selected.get('schemaVersion', 1) != 1:
            raise AppError('INVALID_SELECTION', 'Invalid selection contract.')
        result: list[tuple[str, str]] = []
        seen_episodes: set[str] = set()
        for item in selected['episodes']:
            if set(item) != {'episodeId', 'segmentIds'} or item['episodeId'] in seen_episodes or not item['segmentIds']:
                raise AppError('INVALID_SELECTION', 'Selection episodes must be unique and nonempty.')
            seen_episodes.add(item['episodeId'])
            result.extend((item['episodeId'], sid) for sid in item['segmentIds'])
    else:
        ids = episodes if episodes is not None else [e['id'] for e in story['episodes']]
        if len(ids) != len(set(ids)):
            raise AppError('INVALID_SELECTION', 'Duplicate episode selection.')
        result = []
        for eid in ids:
            episode = next((e for e in story['episodes'] if e['id'] == eid), None)
            if episode is None:
                raise AppError('EPISODE_MISSING', 'Selected episode missing.')
            result.extend((eid, s['id']) for s in episode['segments'])
    if not result or len(result) != len(set(result)):
        raise AppError('INVALID_SELECTION', 'Select unique nonempty segments.')
    for eid, sid in result:
        target(story, eid, sid)
    return result


def capture(story: dict, eid: str, sid: str) -> dict:
    _, segment = target(story, eid, sid)
    bindings(story, segment)
    ids = [ref['assetId'] for ref in segment['references']]
    if segment.get('narration'):
        ids.append(segment['narration']['assetId'])
    assets = [next(a for a in story['assets'] if a['recipe']['assetId'] == asset_id) for asset_id in ids]
    if any(a['media'] is None for a in assets):
        raise AppError('MISSING_ASSET', 'Selected segment has unregistered media.')
    return copy.deepcopy({'episodeId': eid, 'segmentId': sid, 'segment': segment, 'assets': assets})


def validate_source(root: Path, episode: dict) -> None:
    source = episode['source']
    raw = read_stable(project_path(root, source['rawPath']))
    normalized = read_stable(project_path(root, source['textPath']))
    text = normalize_text(raw)
    if sha256(raw) != source['rawHash'] or sha256(normalized) != source['textHash'] or normalized != text.encode('utf-8'):
        raise AppError('SOURCE_CHANGED', 'Source snapshot bytes changed.')
    coverage(text, episode['segments'])
    for segment in episode['segments']:
        span = utf16_slice(text, segment['start'], segment['end'])
        if (episode['kind'] == 'video-prompts' and segment['prompt'] != span) or (episode['kind'] == 'script' and span not in segment['prompt']):
            raise AppError('SOURCE_CHANGED', 'Segment lost its full source span.')


def build_request(root: Path, captured: dict, *, inline: bool = True) -> dict:
    segment = captured['segment']
    if sha256(segment['prompt']) != segment['promptHash']:
        raise AppError('CONTENT_CHANGED', 'Prompt hash mismatch.')
    content: list[dict] = [{'type': 'text', 'text': render_prompt(segment)}]
    if captured.get('derivedPrompt') is not None:
        from ..domain.text import valid_unicode
        text = valid_unicode(captured['derivedPrompt'])
        if not 0 < len(text) <= 7000:
            raise AppError('IR_TEXT_LIMIT', 'Reviewed derived prompt exceeds the request limit.')
        content[0]['text'] = text
    assets = {a['recipe']['assetId']: a for a in captured['assets']}
    refs = [(r['assetId'], r['role']) for r in segment['references']]
    if segment.get('narration'):
        refs.append((segment['narration']['assetId'], 'reference_audio'))
    for asset_id, role in refs:
        media = assets[asset_id]['media']
        audio = role == 'reference_audio'
        data = read_stable(project_path(root, media['path']), MAX_AUDIO if audio else MAX_IMAGE)
        info = audio_info(data) if audio else image_info(data)
        if sha256(data) != media['sha256'] or len(data) != media['bytes'] or any(media.get(k) != v for k, v in info.items()):
            raise AppError('ASSET_CHANGED', 'Registered media bytes or metadata changed.')
        if media['transport'] == 'url':
            from ..providers.http import public_https
            url = public_https(media['url'])
        else:
            url = 'data:' + media['mime'] + ';base64,' + base64.b64encode(data).decode('ascii')
        kind = 'audio_url' if audio else 'image_url'
        content.append({'type': kind, 'role': role, kind: {'url': url}})
    parameters = segment['parameters']
    first = any(r['role'] == 'first_frame' for r in segment['references'])
    ratio = 'adaptive' if first else parameters['ratio']
    if not refs and ratio == 'adaptive':
        raise AppError('H3_RATIO', 'Text generation requires an explicit aspect ratio.')
    request = {'model': 'MiniMax-H3', 'content': content, 'resolution': parameters['resolution'],
               'duration': segment['duration'], 'ratio': ratio, 'context_ir_enabled': inline,
               'aigc_watermark': parameters['watermark']}
    if len(json.dumps(request, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > 64 * 1024 * 1024:
        raise AppError('REQUEST_LIMIT', 'Encoded request exceeds 64 MiB.')
    return request


def prepare(root: Path, episodes: list[str] | None = None, selected: dict | None = None,
            concurrency: int = 4, workflow: str = 'h3-inline-ir') -> dict:
    with lock(project_path(root, f'{STATE}/prepare.lock')):
        return _prepare(root, episodes, selected, concurrency, workflow)


def _prepare(root: Path, episodes: list[str] | None, selected: dict | None,
             concurrency: int, workflow: str) -> dict:
    if type(concurrency) is not int or not 1 <= concurrency <= 4:
        raise AppError('INVALID_INPUT', 'Concurrency must be 1–4.')
    story = load_story(root)
    scope = selection(story, episodes, selected)
    for eid in dict.fromkeys(e for e, _ in scope):
        validate_source(root, next(e for e in story['episodes'] if e['id'] == eid))
    snapshots = [capture(story, eid, sid) for eid, sid in scope]
    scope_hash = digest({'projectId': story['projectId'], 'scope': snapshots, 'concurrency': concurrency, 'workflow': workflow})
    folder = project_path(root, f'{STATE}/batches')
    matching = []
    if folder.exists():
        for file in sorted(folder.glob('*/plan.json')):
            plan = verify(read_json(file), 'batchHash')
            if plan['scopeHash'] == scope_hash:
                matching.append(load_plan(root, file.parent.name))
    if len(matching) > 1:
        raise AppError('SCOPE_AMBIGUOUS', 'More than one frozen plan matches this selection; use an explicit batch ID.')
    if matching:
        return matching[0]
    batch_id = str(uuid.uuid4())
    entries = []
    for snapshot in snapshots:
        request = build_request(root, snapshot, inline=workflow == 'h3-inline-ir')
        request_hash = digest(request)
        # Freeze files by content; never keep every encoded body resident.
        for asset in snapshot['assets']:
            media = asset['media']
            data = read_stable(project_path(root, media['path']), MAX_AUDIO if media['mime'].startswith('audio/') else MAX_IMAGE)
            frozen = f'{STATE}/inputs/{media["sha256"]}.bin'
            existing = project_path(root, frozen)
            if existing.exists() and sha256(read_stable(existing, MAX_IMAGE)) != media['sha256']:
                raise AppError('CONTENT_CHANGED', 'Frozen media snapshot was modified.')
            if not existing.exists():
                atomic_write(existing, data)
            media['path'] = frozen
        entries.append({**snapshot, 'requestHash': request_hash,
                        'inputHash': digest({'requestHash': request_hash, 'sourcePromptHash': snapshot['segment']['promptHash'],
                                            'assets': [(a['recipe']['assetId'], a['recipeHash'], a['media']['sha256']) for a in snapshot['assets']]})})
    plan = sealed({'schemaVersion': 1, 'batchId': batch_id, 'planId': batch_id, 'projectId': story['projectId'],
                   'scopeHash': scope_hash, 'revision': story['revision'], 'manifestHash': digest(story),
                   'createdAt': now(), 'concurrency': concurrency, 'workflow': workflow, 'segments': entries}, 'batchHash')
    with lock(project_path(root, f'{STATE}/story.lock')):
        current = load_story(root)
        if digest(current) != digest(story):
            raise AppError('PLAN_STALE', 'Story changed while preparing; no submission occurred.')
        write_json(project_path(root, f'{STATE}/batches/{batch_id}/plan.json'), plan)
    return plan


def load_plan(root: Path, batch_id: str) -> dict:
    plan = verify(read_json(project_path(root, f'{STATE}/batches/{batch_id}/plan.json')), 'batchHash')
    from ..contracts.records import VideoPlan, validate_record
    validate_record(VideoPlan, plan)
    if plan['batchId'] != batch_id or plan['projectId'] != load_story(root)['projectId']:
        raise AppError('PLAN_IDENTITY', 'Plan belongs to another story.')
    return plan


def assert_current(root: Path, plan: dict, item: dict) -> None:
    story = load_story(root)
    validate_source(root, next(e for e in story['episodes'] if e['id'] == item['episodeId']))
    current = capture(story, item['episodeId'], item['segmentId'])
    expected = item.get('sourceRequestHash', item['requestHash'])
    if story['projectId'] != plan['projectId'] or digest(build_request(root, current, inline=plan['workflow'] == 'h3-inline-ir')) != expected:
        raise AppError('PLAN_STALE', 'Selected prompt or media changed after the plan was frozen.')
    def identities(snapshot):
        return [(a['recipe']['assetId'], a['recipeHash'], a['media']['sha256']) for a in snapshot['assets']]
    if current['segment']['promptHash'] != item['segment']['promptHash'] or identities(current) != identities(item):
        raise AppError('PLAN_STALE', 'Selected source or asset identity differs from the frozen input.')
    if plan['workflow'] == 'h3-context-ir-derived':
        expected_path = f'{STATE}/context-ir/{plan["irOperationId"]}/bindings/{plan["preparePlanId"]}/review.json'
        if plan.get('reviewPath') != expected_path:
            raise AppError('IR_REVIEW', 'Derived review is outside its managed preparation binding.')
        review = verify(read_json(project_path(root, expected_path)))['review']
        if digest(review) != plan['reviewHash'] or review['promptHash'] != sha256(item['derivedPrompt']):
            raise AppError('IR_REVIEW', 'Reviewed IR text identity changed.')
