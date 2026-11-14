"""Pure local 1.1.0 handoff export with per-operation evidence verification."""
import uuid
from pathlib import Path

from ..application.story import MANIFEST, STATE, load_story
from ..domain.errors import AppError
from ..media import handoff
from ..persistence.codec import sealed, sha256, verify
from ..persistence.files import project_path, read_json, read_stable, write_json
from .workflow import collect_images, load_plan


def collect_preparation(root: Path, preparation: str) -> dict:
    folder = project_path(root, f'{STATE}/image-preparations/{preparation}')
    inputs = verify(read_json(folder/'input.json'))
    state = verify(read_json(folder/'state.json'))
    plan = load_plan(root, state['planId'])
    story = load_story(root)
    watched = {}
    def watch(relative, limit=64*1024*1024):
        data = read_stable(project_path(root, relative), limit)
        watched[relative] = sha256(data)
        return data
    watch(MANIFEST)
    summary = collect_images(root, plan['planId'])
    collection = str(uuid.uuid4())
    destination = folder/'collections'/collection
    episodes, exports = [], []
    rows = {r['assetId']: r for r in summary['items']}
    for entry in inputs['entries']:
        request = handoff.validate_request(entry['request'])
        recipe = handoff.validate_recipe(entry['recipe'], request)
        assets, complete = [], True
        for original in recipe['assets']:
            asset_id = original['assetId']
            row = rows.get(asset_id, {})
            out: dict = {key: None for key in handoff.RESULT_ASSET_KEYS}
            out.update(assetId=asset_id, kind=original['kind'], status='blocked', generationMode='not_run',
                       requestedModel=None, executionRelativePath=None, executionSha256=None)
            if original['status'] == 'skipped_optional':
                out['status'] = 'skipped_optional'
            elif original['status'] == 'reused' and row.get('status') == 'reused':
                actual = next(a for a in story['assets'] if a['recipe']['assetId'] == asset_id)['media']
                if not actual or actual['sha256'] != original['contentSha256'] or sha256(watch(actual['path'])) != actual['sha256']:
                    raise AppError('IMAGE_COLLECTION_EVIDENCE', 'Reusable selected file changed.')
                out.update(status='reused', existingRelativePath=actual['path'], contentSha256=actual['sha256'])
            elif row.get('status') == 'registered':
                op = row['operationId']
                jobpath = f'{STATE}/image-jobs/{op}.json'
                watch(jobpath)
                job = verify(read_json(project_path(root, jobpath)))
                execution = f'{STATE}/image-receipts/{op}/execution.json'
                execution_hash = sha256(watch(execution))
                if not job.get('recoveredManually'):
                    receipt_path = f'{STATE}/image-receipts/{op}/complete.json'
                    watch(receipt_path)
                    proof = verify(read_json(project_path(root, receipt_path)))
                    if sha256(watch(f'{STATE}/image-receipts/{op}/response.bin')) != proof['sha256']:
                        raise AppError('IMAGE_COLLECTION_EVIDENCE', 'Original response bytes changed.')
                watch(job['result']['path'])
                watch(job['input']['promptPath'])
                current = next(a for a in story['assets'] if a['recipe']['assetId'] == asset_id)['media']
                if not current or current['sha256'] != job['result']['sha256'] or sha256(watch(current['path'])) != current['sha256']:
                    raise AppError('IMAGE_COLLECTION_EVIDENCE', 'Formal selected result changed.')
                out.update(status='generated', operationId=op, stagedRelativePath=job['result']['path'],
                    contentSha256=job['result']['sha256'], generationPrompt=original['generationPrompt'],
                    recipeSha256=original['recipeSha256'], generationMode='api', requestedModel=job['input']['model'],
                    reportedModel=job.get('reportedModel'), executionRelativePath=execution, executionSha256=execution_hash)
            elif row.get('status') in ('failed', 'rejected'):
                out.update(status='failed', generationMode='api', reason='Known request outcome: '+row['status'])
            else:
                complete = False
                out['reason'] = row.get('status', 'outside_scope')
            assets.append(out)
        path = destination/entry['episodeId']/'reference-image-result.json'
        if complete:
            result = {'schemaVersion': '1.1.0', 'episodeId': entry['episodeId'], 'assets': assets}
            handoff.validate_result(result, request, recipe, root)
            exports.append((path, result))
        episodes.append({'episodeId': entry['episodeId'], 'resultPath': str(path) if complete else None, 'items': assets})
    for relative, expected in watched.items():
        if sha256(read_stable(project_path(root, relative), 64*1024*1024)) != expected:
            raise AppError('IMAGE_COLLECTION_CHANGED', 'Execution changed while sampling; recollect locally.')
    for path, value in exports:
        write_json(path, value)
    report = {'collectionId': collection, 'preparationId': preparation, 'planId': plan['planId'],
              'complete': all(e['resultPath'] is not None for e in episodes), 'episodes': episodes, 'summary': summary}
    write_json(destination/'report.json', sealed(report))
    return report
