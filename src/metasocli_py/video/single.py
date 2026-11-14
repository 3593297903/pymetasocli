import asyncio
import uuid
from pathlib import Path

from ..application.story import STATE
from ..domain.errors import AppError
from ..persistence.codec import digest, sealed, verify
from ..persistence.files import lock, project_path, read_json, write_json
from ..providers.metaso import task_id
from .capacity import Capacity
from .execution import ExecutionOptions, execute_job, publish_event, receipt_path, run_video
from .planning import load_plan, now
from .retry import authorize_retry
from .store import load_job, save_job


async def single_command(root: Path, args, provider, runtime: Path, injected_options=None) -> dict:
    options = injected_options or ExecutionOptions()
    if args.command == 'generate':
        plan = load_plan(root, args.plan)
        if args.segment:
            matches = [s for s in plan['segments'] if s['segmentId'] == args.segment]
            if len(matches) != 1:
                raise AppError('SEGMENT_MISSING', 'Segment is not in the selected plan.')
            item = matches[0]
            if len(plan['segments']) > 1:
                scope_hash = digest({'parent': plan['batchHash'], 'selectedInput': item['inputHash']})
                candidates = [verify(read_json(p), 'batchHash') for p in project_path(root, f'{STATE}/batches').glob('*/plan.json')]
                child = next((p for p in candidates if p['scopeHash'] == scope_hash), None)
                if child is None:
                    identifier = str(uuid.uuid4())
                    child = sealed({**plan, 'batchId': identifier, 'planId': identifier, 'scopeHash': scope_hash,
                                    'concurrency': 1, 'segments': [item], 'createdAt': now()}, 'batchHash')
                    write_json(project_path(root, f'{STATE}/batches/{identifier}/plan.json'), child)
                plan = child
        if args.retry_of:
            authorize_retry(root, plan['batchId'], args.retry_of, args.confirm, args.accept_unknown_result)
        options.submit_only = args.submit_only
        return await run_video(root, plan['batchId'], provider=provider, runtime=runtime,
                               confirm=args.confirm, options=options)
    job = load_job(root, args.operation)
    plan = load_plan(root, job['planId'])
    item = next(s for s in plan['segments'] if s['episodeId'] == job['episodeId'] and s['segmentId'] == job['segmentId'])
    capacity = Capacity(runtime)
    if args.command == 'attach-task':
        if not args.confirm_task_link:
            raise AppError('TASK_LINK_REQUIRED', 'Explicit manual task association is required.')
        identifier = task_id(args.task)
        if job.get('taskId') or job['status'] not in ('submitting', 'submit_unknown'):
            raise AppError('TASK_LINK_REQUIRED', 'Only an unresolved submitted operation without a task ID can be linked.')
        with lock(project_path(root, f'{STATE}/submission.lock'), timeout=0), lock(project_path(root, f'{STATE}/operations/{job["operationId"]}.lock'), timeout=0):
            from ..application.stages import assert_task_available
            assert_task_available(root, identifier, job['operationId'])
            observation = await provider.query(identifier, project_path(root, f'{STATE}/receipts/{job["operationId"]}/manual-query'), job['operationId'], job['requestHash'])
            job['taskId'], job['status'] = identifier, observation['status']
            if observation.get('url'):
                job['resultUrl'] = observation['url']
            write_json(receipt_path(root, job['operationId'], 'create'), sealed({
                **{k: job[k] for k in ('operationId', 'projectId', 'requestHash', 'taskId')},
                'receivedAt': now(), 'recoveredManually': True}))
            save_job(root, job)
            publish_event(root, capacity, job, 'provider_terminal' if job['status'] in ('generated', 'failed', 'cancelled') else 'create_accepted')
        return {'operationId': job['operationId'], 'taskId': identifier, 'recoveredManually': True}
    if args.command == 'status':
        options.max_polls = 1
        options.download_results = False
    with lock(project_path(root, f'{STATE}/submission.lock'), timeout=0), lock(project_path(root, f'{STATE}/operations/{job["operationId"]}.lock'), timeout=0):
        await execute_job(root, plan, item, job, capacity, provider, asyncio.Semaphore(2), options, asyncio.Event())
    return {k: v for k, v in job.items() if k not in ('resultUrl', 'hash', 'hashVersion')}
