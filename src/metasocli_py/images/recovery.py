import asyncio
from pathlib import Path

from ..application.assets import register_asset
from ..application.story import STATE
from ..domain.errors import AppError
from ..media.inspect import image_info
from ..persistence.codec import loads, sealed, sha256, verify
from ..persistence.files import atomic_write, lock, project_path, read_json, read_stable, write_json
from .workflow import (
    Quota,
    collect_images,
    load_image_job,
    load_plan,
    plan_images,
    recover_image,
    run_images,
    save_execution,
    save_job,
)


async def recover_command(root: Path, args, provider, runtime: Path) -> dict:
    job = load_image_job(root, args.operation)
    plan = load_plan(root, job['planId'])
    item = next(i for i in plan['items'] if i['assetId'] == job['assetId'])
    if args.action == 'retry':
        if not args.confirm:
            raise AppError('AUTHORIZATION_REQUIRED', 'One new image attempt requires confirmation.')
        if job['status'] not in ('failed', 'rejected') and not (job['status'] == 'submit_unknown' and args.accept_unknown_result):
            raise AppError('RETRY_NOT_ALLOWED', 'Recover original response before authorizing a new attempt.')
        successor = plan_images(root, assets=[job['assetId']], profile=plan['profile'], restart_of=plan['planId'])
        return await run_images(root, successor['planId'], provider=provider, runtime=runtime, confirm=True, accept_unknown=True,
                                capacity_wait=args.capacity_wait_ms / 1000, capacity_poll=args.capacity_poll_ms / 1000)
    with lock(project_path(root, f'{STATE}/submission.lock'), timeout=0):
        if args.action == 'attach-result':
            if not args.confirm_result_link:
                raise AppError('RESULT_LINK_REQUIRED', 'Explicit result association required.')
            data = read_stable(args.file, plan['profile']['maxImageBytes'])
            info = image_info(data)
            if sha256(data) != args.expected_sha256 or f'{info["width"]}x{info["height"]}' != item['size']:
                raise AppError('IMAGE_RESULT_CHANGED', 'Manual result hash or dimensions mismatch.')
            relative = f'{STATE}/drafts/assets/{job["operationId"]}/manual.image'
            atomic_write(project_path(root, relative), data)
            register_asset(root, item['assetId'], project_path(root, relative), 'user', args.expected_sha256,
                           item['targetHash'], True, item['recipeHash'], job['input']['references'])
            job.update(status='registered', recoveredManually=True,
                       result={'path': relative, **info, 'sha256': sha256(data), 'bytes': len(data)})
            save_job(root, job)
            save_execution(root, job)
        elif args.action == 'resolve':
            if job['status'] != 'submit_unknown':
                raise AppError('RESOLUTION_NOT_ALLOWED', 'Only an unknown submission can be resolved.')
            if not args.confirm_resolution:
                raise AppError('RESOLUTION_REQUIRED', 'Explicit resolution evidence required.')
            evidence = read_json(args.evidence)
            if evidence.get('operationId') != job['operationId'] or evidence.get('requestHash') != job['requestHash'] or evidence.get('outcome') != args.outcome:
                raise AppError('RESOLUTION_IDENTITY', 'Evidence belongs to another request.')
            source = evidence.get('source', {})
            if source.get('kind') not in ('provider-support', 'provider-request-log', 'provider-api-response') or not source.get('reference') or not source.get('statement'):
                raise AppError('RESOLUTION_SOURCE', 'Explicit provider evidence is required.')
            independent = False
            if source['kind'] == 'provider-api-response':
                relative = f'{STATE}/image-receipts/{job["operationId"]}/complete.json'
                proof = verify(read_json(project_path(root, relative)))
                raw = read_stable(project_path(root, f'{STATE}/image-receipts/{job["operationId"]}/response.bin'), plan['profile']['maxResponseBytes'])
                if source['reference'] != relative or proof['requestHash'] != job['requestHash'] or proof['sha256'] != sha256(raw):
                    raise AppError('RESOLUTION_IDENTITY', 'Complete provider response identity mismatch.')
                error = loads(raw).get('error', {})
                interrupted = proof['httpStatus'] == 503 and args.outcome == 'failed' and error.get('code') == 'task_interrupted' and error.get('type') == 'server_error'
                rejected_edit = proof['httpStatus'] == 500 and args.outcome == 'not-created' and job['input']['route'] == '/v1/images/edits' and bool(job['input']['references']) and error.get('code') == 'convert_request_failed' and error.get('type') == 'new_api_error' and str(error.get('message', '')).startswith('image is required')
                refused = proof['httpStatus'] == 400 and args.outcome == 'failed' and error.get('type') == 'invalid_request_error' and error.get('code') == 'upstream_text_reply' and ('内容政策' in str(error.get('message', '')) or 'content policy' in str(error.get('message', '')).lower())
                if not (interrupted or rejected_edit or refused):
                    raise AppError('RESOLUTION_UNPROVEN', 'Response does not prove termination or pre-generation rejection.')
                independent = True
            write_json(project_path(root, f'{STATE}/image-receipts/{job["operationId"]}/resolution.json'),
                       sealed({**evidence, 'independentlyVerified': independent, 'userReported': not independent}))
            job['status'] = 'rejected' if args.outcome == 'not-created' else 'failed'
            save_job(root, job)
        else:
            await recover_image(root, job, item, plan['profile'], provider, asyncio.Semaphore(2), asyncio.Semaphore(2), asyncio.Semaphore(1))
        Quota(runtime, plan['profile'], root).update(job)
    return collect_images(root, plan['planId'])
