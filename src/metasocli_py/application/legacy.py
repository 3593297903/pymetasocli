"""Read-only inspection and explicit content-only import of static legacy stories."""
import copy
from pathlib import Path

from ..domain.errors import AppError
from ..persistence.codec import HASH_VERSION, digest, dumps, loads, sealed, sha256
from ..persistence.files import lock, project_path, read_stable, safe_path, transaction
from .story import MANIFEST, STATE, initialize, load_story


def inspect_legacy(source: Path) -> dict:
    source = safe_path(source)
    raw = read_stable(project_path(source, 'metasocli.yaml'))
    story = loads(raw, yaml_input=True)
    if story.get('owner') != 'metasocli' or story.get('schemaVersion') != 1:
        raise AppError('LEGACY_FORMAT', 'Expected an explicit legacy metasocli story.')
    unresolved = []
    fingerprints = {'metasocli.yaml': sha256(raw)}
    for category in ('jobs', 'image-jobs', 'context-ir'):
        folder = project_path(source, f'.metasocli/{category}')
        if folder.exists():
            for file in folder.rglob('*.json'):
                data = read_stable(file)
                record = loads(data)
                fingerprints[str(file.relative_to(source))] = sha256(data)
                if isinstance(record, dict) and record.get('status') in ('prepared', 'submitting', 'submit_unknown', 'query_unknown', 'queued', 'running', 'response_saved', 'received'):
                    unresolved.append({'operationId': record.get('operationId'), 'status': record['status']})
    state = project_path(source, '.metasocli')
    if state.exists() and any(state.rglob('*.lock')):
        unresolved.append({'operationId': None, 'status': 'legacy_lock_present'})
    paths = [e['source'][key] for e in story['episodes'] for key in ('rawPath', 'textPath')]
    paths += [a['media']['path'] for a in story['assets'] if a['media']]
    for path in paths:
        fingerprints[path] = sha256(read_stable(project_path(source, path), 30*1024*1024))
    return {'projectId': story.get('projectId'), 'episodes': len(story.get('episodes', [])),
            'assets': len(story.get('assets', [])), 'eligible': not unresolved, 'unresolved': unresolved, 'fingerprints': fingerprints}


def import_content(source: Path, root: Path, name: str) -> dict:
    source, root = safe_path(source), safe_path(root)
    if root == source or root.is_relative_to(source) or source.is_relative_to(root):
        raise AppError('LEGACY_OVERLAP', 'Legacy import requires disjoint directories.')
    before = inspect_legacy(source)
    if not before['eligible']:
        raise AppError('LEGACY_ACTIVE', 'Legacy active or unknown tasks must be resolved in the old engine.')
    story = copy.deepcopy(loads(read_stable(source / 'metasocli.yaml'), yaml_input=True))
    writes = {}
    from ..media.inspect import audio_info, image_info
    for episode in story['episodes']:
        episode['offsetEncoding'] = 'utf16'
        for pathkey, hashkey in [('rawPath', 'rawHash'), ('textPath', 'textHash')]:
            data = read_stable(project_path(source, episode['source'][pathkey]))
            if sha256(data) != episode['source'][hashkey]:
                raise AppError('LEGACY_CHANGED', 'Legacy source checksum mismatch.')
            newpath = episode['source'][pathkey].replace('.metasocli/', STATE + '/', 1)
            episode['source'][pathkey] = newpath
            writes[newpath] = data
    for asset in story['assets']:
        asset['recipeHash'] = digest(asset['recipe'])
        if asset['media']:
            media = asset['media']
            data = read_stable(project_path(source, media['path']), 30*1024*1024)
            info = audio_info(data) if asset['recipe']['kind'] == 'narration' else image_info(data)
            if sha256(data) != media['sha256'] or any(media.get(k) != v for k, v in info.items()):
                raise AppError('LEGACY_CHANGED', 'Legacy media checksum/metadata mismatch.')
            # Imported content is local-only, with no legacy signed URL coupling.
            media['transport'] = 'data'
            media.pop('url', None)
            writes[media['path']] = data
    if inspect_legacy(source) != before:
        raise AppError('LEGACY_CHANGED', 'Legacy story changed during inspection.')
    initialized = initialize(root, name)
    story.update(owner='metasocli-py', hashVersion=HASH_VERSION, projectId=initialized['projectId'], name=name, revision=0)
    from ..contracts.story import Manifest, parse
    parse(Manifest, story)
    writes[f'{STATE}/legacy-source.json'] = dumps(sealed({'sourceProjectId': before['projectId'],
        'newProjectId': story['projectId'], 'fingerprints': before['fingerprints'], 'tasksImported': False}))
    writes[MANIFEST] = dumps(story)
    with lock(project_path(root, f'{STATE}/story.lock')):
        transaction(root, writes, MANIFEST)
    load_story(root)
    return {'projectId': story['projectId'], 'sourceProjectId': before['projectId'], 'tasksImported': False}
