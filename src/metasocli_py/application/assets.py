from pathlib import Path

from ..contracts.story import Manifest, parse
from ..domain.errors import AppError
from ..media.inspect import MAX_AUDIO, MAX_IMAGE, audio_info, image_info
from ..persistence.codec import dumps, sha256
from ..persistence.files import lock, project_path, read_stable, recover_transactions, transaction
from .story import MANIFEST, STATE, load_story


def register_asset(root: Path, asset_id: str, file: Path, provenance: str = 'user',
                   expected_sha256: str | None = None, expected_media: str | None = None,
                   enforce_media: bool = False, expected_recipe: str | None = None,
                   dependencies: list[dict] | None = None, url: str | None = None) -> dict:
    declared = next((a for a in load_story(root)['assets'] if a['recipe']['assetId'] == asset_id), None)
    if declared is None:
        raise AppError('MISSING_RECIPE', 'Declare asset recipe before registering media.')
    audio = declared['recipe']['kind'] == 'narration'
    if audio and provenance != 'user':
        raise AppError('ASSET_ROLE', 'Narration must be user-provided.')
    data = read_stable(file, MAX_AUDIO if audio else MAX_IMAGE)
    info = audio_info(data) if audio else image_info(data)
    h = sha256(data)
    if expected_sha256 and expected_sha256 != h:
        raise AppError('ASSET_CHANGED', 'Selected media SHA-256 mismatch.')
    extension = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp', 'audio/mpeg': 'mp3', 'audio/wav': 'wav'}[info['mime']]
    media = {**info, 'path': f'assets/{asset_id}/{h}.{extension}', 'sha256': h, 'bytes': len(data),
             'provenance': provenance, 'transport': 'url' if url else 'data', **({'url': url} if url else {})}
    with lock(project_path(root, f'{STATE}/story.lock')):
        recover_transactions(root)
        story = load_story(root)
        asset = next(a for a in story['assets'] if a['recipe']['assetId'] == asset_id)
        if asset['recipeHash'] != declared['recipeHash']:
            raise AppError('RECIPE_CONFLICT', 'Recipe changed while reading media.')
        if expected_recipe and asset['recipeHash'] != expected_recipe:
            raise AppError('IMAGE_PLAN_STALE', 'The selected recipe differs from the generated result.')
        for dependency in dependencies or []:
            selected = next((a['media'] for a in story['assets'] if a['recipe']['assetId'] == dependency['assetId']), None)
            if selected is None or selected['sha256'] != dependency['sha256'] or sha256(read_stable(project_path(root, selected['path']), MAX_IMAGE)) != dependency['sha256']:
                raise AppError('IMAGE_DEPENDENCY_CHANGED', 'The generated image used an obsolete reference.')
        current_hash = asset['media']['sha256'] if asset['media'] else None
        if enforce_media and current_hash not in (expected_media, h):
            raise AppError('IMAGE_SUPERSEDED', 'A new user selection superseded the generated result.')
        if enforce_media and current_hash == h:
            media = asset['media']  # Preserve an explicit user selection of this exact result.
        changed = asset['media'] != media
        if changed:
            asset['media'] = media
            story['revision'] += 1
        parse(Manifest, story)
        transaction(root, {media['path']: data, MANIFEST: dumps(story)}, MANIFEST)
        return {'schemaVersion': 1, 'assetId': asset_id, 'changed': changed, 'revision': story['revision'], 'media': media}


def inspect_assets(root: Path) -> list[dict]:
    result = []
    for asset in load_story(root)['assets']:
        status = 'missing'
        media = asset['media']
        if media:
            try:
                status = 'ready' if sha256(read_stable(project_path(root, media['path']), MAX_IMAGE)) == media['sha256'] else 'changed'
            except (OSError, AppError):
                status = 'changed'
        result.append({'assetId': asset['recipe']['assetId'], 'kind': asset['recipe']['kind'], 'status': status})
    return result
