"""Explicit independent IR compatibility branch; never invoked by video run."""
import asyncio
import re
import uuid
from pathlib import Path

from ..application.story import STATE
from ..contracts.records import IrOperation, validate_record
from ..domain.errors import AppError
from ..domain.text import utf16_slice, valid_unicode
from ..persistence.codec import digest, loads, sealed, sha256, verify
from ..persistence.files import atomic_write, lock, project_path, read_json, read_stable, write_json
from ..providers.http import ProviderError
from .planning import assert_current, build_request, load_plan, now


def read_ir(root: Path, operation: str) -> dict:
    record = validate_record(IrOperation, verify(read_json(project_path(root, f'{STATE}/context-ir/{operation}/operation.json'))))
    plan = load_plan(root, record['planId'])
    item = next((s for s in plan['segments'] if s['episodeId'] == record['episodeId'] and s['segmentId'] == record['segmentId']), None)
    if (record['operationId'] != operation or record['projectId'] != plan['projectId']
        or record['planHash'] != plan['batchHash'] or plan['workflow'] != 'h3-context-ir'
        or item is None or record['baseInputHash'] != item['inputHash']):
        raise AppError('IR_JOB_IDENTITY', 'Independent IR operation does not match its frozen preparation.')
    if record['status'] in ('queued', 'running', 'query_unknown', 'enhanced') and not record.get('taskId'):
        raise AppError('IR_JOB_IDENTITY', 'Accepted IR operation lacks its task ID.')
    expected_path = f'{STATE}/context-ir/{operation}/enhanced.txt'
    if record.get('resultPath') not in (None, expected_path) or (record['status'] == 'enhanced' and not record.get('promptHash')):
        raise AppError('IR_RESULT_IDENTITY', 'Independent IR result has an invalid managed identity.')
    return record


def validate_review(text: str, item: dict, review: dict, allow_needs_review: bool = False) -> None:
    valid_unicode(text)
    if not text.strip() or len(text) > 7000 or '{{' in text or '}}' in text:
        raise AppError('IR_TEXT_LIMIT', 'Enhanced text is invalid or contains unresolved references.')
    required = {'schemaVersion', 'operationId', 'promptHash', 'verdict', 'reviewer', 'findings', 'dialogueQuotes'}
    if set(review) != required or type(review['schemaVersion']) is not int or review['schemaVersion'] != 1 or review['verdict'] not in ('approved', 'needs_review') or not review['reviewer']:
        raise AppError('IR_REVIEW', 'Explicit approved semantic review is required.')
    if set(review['findings']) != {'dialogue', 'references', 'narration', 'constraints'} or not all(isinstance(v, str) and v.strip() for v in review['findings'].values()):
        raise AppError('IR_REVIEW', 'Concrete review findings are required.')
    if review['promptHash'] != sha256(text):
        raise AppError('IR_REVIEW', 'Review belongs to another enhanced text.')
    if review['verdict'] == 'needs_review':
        if allow_needs_review:
            return
        raise AppError('IR_REVIEW', 'Semantic review requires further work before deriving video.')
    segment = item['segment']
    quotes = list(review['dialogueQuotes'])
    quotes += [next(q for q in groups if q) for groups in re.findall(r'“([^”]+)”|「([^」]+)」|"([^"\n]+)"', segment['prompt'])]
    if any(not isinstance(q, str) or not q or q not in segment['prompt'] or q not in text for q in quotes):
        raise AppError('IR_DIALOGUE', 'Enhanced text omitted source dialogue.')
    cursor = 0
    for quote in review['dialogueQuotes'] + [utf16_slice(segment['prompt'], c['start'], c['end']) for c in (segment.get('narration') or {}).get('cues', [])]:
        index = text.find(quote, cursor)
        if index < 0:
            raise AppError('IR_DIALOGUE', 'Dialogue/narration order changed.')
        cursor = index + len(quote)
    for index in re.findall(r'(?:参考图|reference\s*image)\s*(\d+)', text, re.I):
        number = int(index)
        if not 1 <= number <= len(segment['references']) or segment['references'][number-1]['role'] != 'reference_image':
            raise AppError('IR_REFERENCE', 'Enhanced text refers to an unbound image.')
    for index in re.findall(r'(?:参考音频|reference\s*audio)\s*(\d+)', text, re.I):
        if not segment.get('narration') or int(index) != 1:
            raise AppError('IR_REFERENCE', 'Enhanced text refers to an unbound audio input.')
    if '首帧图片' in text and not any(r['role'] == 'first_frame' for r in segment['references']):
        raise AppError('IR_REFERENCE', 'Enhanced text refers to an unbound first frame.')


async def ir_command(root: Path, args, provider) -> dict:
    if args.action == 'status':
        return await _ir_command(root, args, provider)
    with lock(project_path(root, f'{STATE}/submission.lock'), timeout=0):
        return await _ir_command(root, args, provider)


async def _ir_command(root: Path, args, provider) -> dict:
    from ..application.stages import assert_task_available, new_submission
    from ..providers.metaso import extract_id, task_id
    polls, poll_seconds = getattr(args, 'max_polls', 60), getattr(args, 'poll_ms', 5000)/1000
    if type(polls) is not int or not 1 <= polls <= 720 or not 0 <= poll_seconds <= 60:
        raise AppError('INVALID_INPUT', 'Invalid independent IR polling budget.')
    folder = project_path(root, f'{STATE}/context-ir')
    if args.action == 'run':
        if not args.confirm or not args.plan or not args.segment:
            raise AppError('AUTHORIZATION_REQUIRED', 'Explicit IR plan, segment and confirmation are required.')
        plan = load_plan(root, args.plan)
        if plan['workflow'] != 'h3-context-ir':
            raise AppError('IR_MODE_CONFLICT', 'Independent IR requires its explicitly prepared workflow.')
        matches = [s for s in plan['segments'] if s['segmentId'] == args.segment]
        if len(matches) != 1:
            raise AppError('SEGMENT_MISSING', 'Selected IR segment missing.')
        item = matches[0]
        base = build_request(root, item, inline=False)
        request = {k: base[k] for k in ('model', 'content', 'duration', 'ratio')}
        request_hash = digest(request)
        records = [read_ir(root, p.parent.name) for p in folder.glob('*/operation.json')] if folder.exists() else []
        matching = [r for r in records if r['requestHash'] == request_hash and r['baseInputHash'] == item['inputHash'] and r['segmentId'] == item['segmentId'] and r['episodeId'] == item['episodeId']]
        record = max(matching, key=lambda r: r['attempt'], default=None)
        retry_of = getattr(args, 'retry_of', None)
        if retry_of:
            repeated = next((r for r in matching if r.get('retryOf') == retry_of), None)
            if repeated:
                record = repeated
            elif record and record['operationId'] == retry_of and record['status'] in ('failed', 'cancelled'):
                record = None
            else:
                raise AppError('IR_RETRY_NOT_ALLOWED', 'Only the latest definitively failed IR attempt may be retried.')
        if record is None:
            if any(r['status'] in ('submitting', 'submit_unknown', 'query_unknown', 'queued', 'running') for r in records):
                raise AppError('IR_UNRESOLVED', 'Resolve the existing independent IR operation first.')
            operation = str(uuid.uuid4())
            new_submission(root, 'ir')
            assert_current(root, plan, item)
            for asset in item['assets']:
                media = asset['media']
                if media['transport'] == 'url':
                    check = project_path(root, f'{STATE}/media-checks/{operation}-{media["sha256"]}.bin')
                    await provider.http.download(media['url'], check, limit=media['bytes'], redirects=0)
                    if sha256(read_stable(check, media['bytes'])) != media['sha256']:
                        raise AppError('REMOTE_MEDIA_CHANGED', 'Remote IR input bytes changed.')
            record = {'operationId': operation, 'projectId': plan['projectId'], 'planId': plan['batchId'],
                      'planHash': plan['batchHash'], 'episodeId': item['episodeId'], 'segmentId': item['segmentId'], 'requestHash': request_hash,
                      'baseInputHash': item['inputHash'],
                      'attempt': max((r['attempt'] for r in matching), default=0)+1, **({'retryOf': retry_of} if retry_of else {}),
                      'status': 'submitting', 'createdAt': now()}
            recordfile = project_path(folder, f'{operation}/operation.json')
            write_json(recordfile, sealed(record))
            try:
                identifier = await provider.create(request, recordfile.parent / 'create', operation, request_hash, ir=True)
                assert_task_available(root, identifier, operation)
                record.update(taskId=identifier, status='queued')
                write_json(recordfile.parent / 'receipt.json', sealed({'operationId': operation, 'requestHash': request_hash, 'taskId': identifier}))
            except (AppError, ProviderError) as error:
                record['status'] = 'failed' if isinstance(error, ProviderError) and error.rejected else 'submit_unknown'
                record['error'] = {'code': error.code, 'message': error.message}
            except asyncio.CancelledError:
                record['status'] = 'submit_unknown'
                write_json(recordfile, sealed(record))
                raise
            write_json(recordfile, sealed(record))
    else:
        if not args.operation:
            raise AppError('INVALID_INPUT', 'Exact IR operation ID required.')
        record = read_ir(root, args.operation)
        plan = load_plan(root, record['planId'])
        item = next(s for s in plan['segments'] if s['segmentId'] == record['segmentId'] and s['episodeId'] == record['episodeId'])
    recordfile = project_path(folder, f'{record["operationId"]}/operation.json')
    if args.action in ('run', 'resume') and not record.get('taskId'):
        complete = recordfile.parent/'create/complete.json'
        if complete.exists():
            proof = verify(read_json(complete))
            raw = read_stable(recordfile.parent/'create/response.bin')
            if proof['operationId'] != record['operationId'] or proof['requestHash'] != record['requestHash'] or proof['sha256'] != sha256(raw):
                raise AppError('IR_RECEIPT_IDENTITY', 'Complete IR response identity mismatch.')
            if 200 <= proof['httpStatus'] < 300:
                identifier = extract_id(loads(raw), ir=True)
                assert_task_available(root, identifier, record['operationId'])
                record.update(taskId=identifier, status='queued')
                write_json(recordfile.parent/'receipt.json', sealed({'operationId': record['operationId'], 'requestHash': record['requestHash'], 'taskId': identifier}))
                write_json(recordfile, sealed(record))
        elif record['status'] == 'submitting':
            record['status'] = 'submit_unknown'
            write_json(recordfile, sealed(record))
    if args.action == 'attach-task':
        if not args.confirm or record.get('taskId') or record['status'] not in ('submitting', 'submit_unknown'):
            raise AppError('IR_TASK_LINK_REQUIRED', 'Explicit link requires an unresolved IR operation without task ID.')
        identifier = task_id(args.task)
        assert_task_available(root, identifier, record['operationId'])
        await provider.query(identifier, recordfile.parent/'manual-query', record['operationId'], record['requestHash'], ir=True)
        record.update(taskId=identifier, status='queued', recoveredManually=True)
        write_json(recordfile.parent/'receipt.json', sealed({'operationId': record['operationId'], 'requestHash': record['requestHash'], 'taskId': identifier}))
        write_json(recordfile, sealed(record))
    if getattr(args, 'submit_only', False):
        return record
    resultfile = recordfile.parent/'result.json'
    if args.action in ('run', 'resume') and resultfile.exists():
        result = verify(read_json(resultfile))
        if any(result[k] != record.get(k) for k in ('operationId', 'requestHash', 'taskId')):
            raise AppError('IR_RESULT_IDENTITY', 'Saved IR text receipt identity mismatch.')
        text = read_stable(project_path(root, result['resultPath'])).decode('utf-8')
        if sha256(text) != result['promptHash']:
            raise AppError('IR_TEXT_CHANGED', 'Saved enhanced text changed.')
        record.update(status='enhanced', resultPath=result['resultPath'], promptHash=result['promptHash'])
        write_json(recordfile, sealed(record))
    if args.action in ('run', 'resume') and record.get('taskId') and record['status'] not in ('enhanced', 'failed', 'cancelled'):
        for index in range(polls):
            try:
                observation = await provider.query(record['taskId'], recordfile.parent / f'query-{uuid.uuid4()}', record['operationId'], record['requestHash'], ir=True)
                record['status'] = observation['status']
                if observation['status'] == 'generated':
                    text = valid_unicode(observation['prompt'])
                    path = recordfile.parent / 'enhanced.txt'
                    atomic_write(path, text.encode('utf-8'))
                    write_json(resultfile, sealed({**{k: record[k] for k in ('operationId', 'requestHash', 'taskId')},
                        'resultPath': str(path.relative_to(root)).replace('\\', '/'), 'promptHash': sha256(text)}))
                    record.update(status='enhanced', resultPath=str(path.relative_to(root)).replace('\\', '/'), promptHash=sha256(text))
                write_json(recordfile, sealed(record))
                if record['status'] in ('enhanced', 'failed', 'cancelled'):
                    break
                if index + 1 < polls:
                    await asyncio.sleep(poll_seconds)
            except AppError as error:
                record.update(status='query_unknown', error={'code': error.code, 'message': error.message})
                write_json(recordfile, sealed(record))
                break
        else:
            record['error'] = {'code': 'POLL_LIMIT', 'message': 'Local IR polling budget ended; resume the same task.'}
            write_json(recordfile, sealed(record))
    if args.action in ('review', 'derive'):
        if record['status'] != 'enhanced':
            raise AppError('IR_NOT_READY', 'IR text is not available for review.')
        if getattr(args, 'plan', None):
            plan = load_plan(root, args.plan)
            item = next((s for s in plan['segments'] if s['episodeId'] == record['episodeId'] and s['segmentId'] == record['segmentId']), None)
            if plan['workflow'] != 'h3-context-ir' or item is None or item['inputHash'] != record['baseInputHash']:
                raise AppError('IR_PROVENANCE', 'Saved IR may only bind an equivalent selected preparation input.')
        assert_current(root, plan, item)
        text = read_stable(project_path(root, record['resultPath'])).decode('utf-8')
        if sha256(text) != record['promptHash']:
            raise AppError('IR_TEXT_CHANGED', 'Saved enhanced text changed.')
        binding = recordfile.parent/'bindings'/plan['batchId']
        reviewfile = binding/'review.json'
        derivedfile = binding/'derived-plan.json'
        review = read_json(args.file) if args.action == 'review' and args.file else verify(read_json(reviewfile))['review']
        if review.get('operationId') != record['operationId']:
            raise AppError('IR_REVIEW', 'Review operation mismatch.')
        validate_review(text, item, review, allow_needs_review=args.action == 'review')
        if args.action == 'review':
            if derivedfile.exists() and verify(read_json(derivedfile), 'batchHash')['reviewHash'] != digest(review):
                raise AppError('IR_REVIEW', 'An existing derived plan reserves its immutable review.')
            write_json(reviewfile, sealed({'review': review, 'reviewedAt': now()}))
            return {'operationId': record['operationId'], 'reviewed': True}
        request = build_request(root, item, inline=False)
        request['content'][0]['text'] = text
        if derivedfile.exists():
            derived = verify(read_json(derivedfile), 'batchHash')
            if derived['reviewHash'] != digest(review):
                raise AppError('IR_REVIEW', 'Existing derived plan belongs to another review.')
        else:
            batch_id = str(uuid.uuid4())
            captured = {**item, 'derivedPrompt': text, 'sourceRequestHash': item['requestHash'],
                        'requestHash': digest(request), 'inputHash': digest({'request': digest(request), 'review': digest(review)})}
            derived = sealed({**{k: plan[k] for k in ('schemaVersion', 'projectId', 'revision', 'manifestHash')},
                'batchId': batch_id, 'planId': batch_id, 'createdAt': now(), 'concurrency': 1,
                'scopeHash': digest({'parent': plan['batchHash'], 'review': digest(review)}),
                'preparePlanId': plan['batchId'], 'irOperationId': record['operationId'],
                'reviewPath': str(reviewfile.relative_to(root)).replace('\\', '/'),
                'reviewHash': digest(review), 'workflow': 'h3-context-ir-derived', 'segments': [captured]}, 'batchHash')
            write_json(derivedfile, derived)
        write_json(project_path(root, f'{STATE}/batches/{derived["batchId"]}/plan.json'), derived)
        return {'operationId': record['operationId'], 'planId': derived['batchId'], 'videoRequiresSeparateConfirmation': True}
    return {k: v for k, v in record.items() if k not in ('hash', 'hashVersion')}
