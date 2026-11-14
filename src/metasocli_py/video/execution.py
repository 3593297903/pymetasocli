import asyncio
import time
import uuid
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..application.story import STATE
from ..contracts.records import VideoRun, validate_record
from ..domain.errors import AppError
from ..media.inspect import MAX_VIDEO, video_info
from ..persistence.codec import digest, sealed, sha256, verify
from ..persistence.files import lock, project_path, read_json, read_stable, replace_file, write_json
from ..providers.http import ProviderError
from ..providers.metaso import Metaso, extract_id
from .capacity import Capacity
from .planning import assert_current, build_request, load_plan, now
from .store import find_jobs, load_job, save_job


@dataclass
class ExecutionOptions:
    max_polls: int = 60
    poll_seconds: float = 5
    capacity_wait: float = 30
    capacity_poll: float = .25
    submit_only: bool = False
    download_results: bool = True
    checkpoint: Callable[[str, dict], None] = field(default=lambda _point, _job: None)


def receipt_path(root: Path, operation: str, kind: str) -> Path:
    return project_path(root, f'{STATE}/receipts/{operation}-{kind}.json')


def publish_event(root: Path, capacity: Capacity, job: dict, reason: str, sequence: int | None = None) -> None:
    sequence = capacity.issue(job['operationId']) if sequence is None else sequence
    event = sealed({**{k: job[k] for k in ('operationId', 'projectId', 'requestHash')},
        'sequence': sequence, 'reason': reason, **({'taskId': job['taskId']} if job.get('taskId') else {})})
    # Persist story evidence, release story lock, then apply runtime transaction.
    with lock(project_path(root, f'{STATE}/story.lock')):
        path = receipt_path(root, job['operationId'], 'capacity')
        prior = verify(read_json(path)) if path.exists() else None
        if prior and (prior['reason'] == 'provider_terminal' or (prior['sequence'] >= sequence and reason != 'provider_terminal')):
            event = prior
        else:
            write_json(path, event)
    capacity.apply(event)


def reconcile_create(root: Path, job: dict) -> None:
    from ..application.stages import assert_task_available
    receipt = receipt_path(root, job['operationId'], 'create')
    if receipt.exists():
        saved = verify(read_json(receipt))
        if any(saved.get(k) != job[k] for k in ('operationId', 'projectId', 'requestHash')) or job.get('taskId') not in (None, saved['taskId']):
            raise AppError('RECEIPT_IDENTITY', 'Creation receipt identity conflict.')
        if not job.get('taskId'):
            assert_task_available(root, saved['taskId'], job['operationId'])
            job['taskId'], job['status'] = saved['taskId'], 'queued'
            save_job(root, job)
        return
    folder = project_path(root, f'{STATE}/receipts/{job["operationId"]}/create')
    complete = folder / 'complete.json'
    if complete.exists():
        from ..persistence.codec import loads, sha256
        from ..persistence.files import read_stable
        metadata = verify(read_json(complete))
        data = read_stable(folder / 'response.bin')
        if metadata['operationId'] != job['operationId'] or metadata['requestHash'] != job['requestHash'] or metadata['sha256'] != sha256(data):
            raise AppError('RECEIPT_IDENTITY', 'Complete response identity mismatch.')
        if 200 <= metadata['httpStatus'] < 300:
            identifier = extract_id(loads(data))
            assert_task_available(root, identifier, job['operationId'])
            write_json(receipt, sealed({**{k: job[k] for k in ('operationId', 'projectId', 'requestHash')},
                                      'taskId': identifier, 'receivedAt': now()}))
            job['taskId'], job['status'] = identifier, 'queued'
            save_job(root, job)


def reconcile_output(root: Path, job: dict) -> dict | None:
    path = receipt_path(root, job['operationId'], 'download')
    if not path.exists():
        if job.get('output'):
            raise AppError('OUTPUT_RECEIPT_MISSING', 'Output receipt missing; recover original task.')
        return None
    record = verify(read_json(path))
    if any(record.get(k) != job.get(k) for k in ('operationId', 'taskId', 'requestHash')):
        raise AppError('OUTPUT_CONFLICT', 'Download receipt identity mismatch.')
    output = record['output']
    destination = project_path(root, output['path'])
    staged = project_path(root, record['stagedPath'])
    if not destination.exists() and staged.exists():
        actual = video_info(staged)
        if any(actual[k] != output[k] for k in actual):
            raise AppError('OUTPUT_CHANGED', 'Staged video differs from receipt.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        replace_file(staged, destination)
    if not destination.exists():
        return None
    actual = video_info(destination)
    if any(actual[k] != output[k] for k in actual):
        raise AppError('OUTPUT_CHANGED', 'Saved output differs from receipt; preserve it for recovery.')
    return output


async def download(root: Path, job: dict, item: dict, provider: Metaso, semaphore: asyncio.Semaphore,
                   options: ExecutionOptions) -> None:
    async with semaphore:
        existing = await asyncio.to_thread(reconcile_output, root, job)
        if existing is not None:
            job['output'], job['status'] = existing, 'downloaded'
            save_job(root, job)
            return
        url = job.get('resultUrl')
        if not isinstance(url, str):
            raise AppError('RESULT_METADATA', 'Trusted terminal state lacks a usable video URL.')
        job['timings']['downloadStart'] = time.perf_counter()
        relative = f'outputs/{job["episodeId"]}/{job["segmentId"]}-{job["operationId"]}.mp4'
        destination = project_path(root, relative)
        staged_relative = f'{STATE}/downloads/{job["operationId"]}.mp4'
        staged = project_path(root, staged_relative)
        meta = await provider.http.download(url, staged, limit=MAX_VIDEO)
        mime = meta['headers'].get('content-type', 'application/octet-stream').split(';')[0]
        if mime not in ('video/mp4', 'application/octet-stream'):
            raise AppError('VIDEO_INVALID', 'Unexpected video response MIME.')
        actual = await asyncio.to_thread(video_info, staged)
        expected = item['segment']['duration']
        if abs(actual['duration'] - expected) > 1:
            raise AppError('VIDEO_DURATION', 'Video duration differs from frozen plan.')
        ratio = 'adaptive' if any(r['role'] == 'first_frame' for r in item['segment']['references']) else item['segment']['parameters']['ratio']
        if ratio != 'adaptive':
            w, h = map(int, ratio.split(':'))
            if abs(actual['width'] / actual['height'] / (w/h) - 1) > .03:
                raise AppError('VIDEO_RATIO', 'Video aspect ratio differs from frozen plan.')
        output = {'path': relative, **actual}
        write_json(receipt_path(root, job['operationId'], 'download'), sealed({
            **{k: job[k] for k in ('operationId', 'taskId', 'requestHash')},
            'output': output, 'stagedPath': staged_relative}))
        options.checkpoint('download-before-rename', job)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise AppError('OUTPUT_CONFLICT', 'Output appeared during download.')
        replace_file(staged, destination)
        options.checkpoint('download-after-rename', job)
        job['output'], job['status'] = output, 'downloaded'
        job['timings']['downloadComplete'] = time.perf_counter()
        save_job(root, job)


async def execute_job(root: Path, plan: dict, item: dict, job: dict, capacity: Capacity,
                      provider: Metaso, downloads: asyncio.Semaphore, options: ExecutionOptions,
                      changed: asyncio.Event, *, submit: bool = False, owner_lease: ExitStack | None = None,
                      queries: asyncio.Semaphore | None = None) -> None:
    operation = job['operationId']
    try:
        if submit:
            with owner_lease if owner_lease is not None else lock(capacity.root / 'owners' / f'{operation}.lock', timeout=0):
                assert_current(root, plan, item)
                for asset in item['assets']:
                    media = asset['media']
                    if media['transport'] == 'url':
                        check = project_path(root, f'{STATE}/media-checks/{operation}-{media["sha256"]}.bin')
                        await provider.http.download(media['url'], check, limit=media['bytes'], redirects=0)
                        if sha256(read_stable(check, media['bytes'])) != media['sha256']:
                            raise AppError('REMOTE_MEDIA_CHANGED', 'Remote input bytes differ from the frozen plan.')
                request = build_request(root, item, inline=plan['workflow'] == 'h3-inline-ir')
                if digest(request) != job['requestHash']:
                    raise AppError('PLAN_STALE', 'Frozen input bytes changed.')
                job.update(status='submitting', submittedAt=now())
                job['timings']['intent'] = time.perf_counter()
                save_job(root, job)
                options.checkpoint('after-intent', job)
                job['timings']['send'] = time.perf_counter()
                try:
                    identifier = await provider.create(request, project_path(root, f'{STATE}/receipts/{operation}/create'), operation, job['requestHash'])
                    from ..application.stages import assert_task_available
                    assert_task_available(root, identifier, operation)
                except (ProviderError, AppError) as error:
                    job['status'] = 'failed' if isinstance(error, ProviderError) and error.rejected else 'submit_unknown'
                    job['error'] = {'code': error.code, 'message': error.message}
                    if isinstance(error, ProviderError) and error.status is not None:
                        job['error']['httpStatus'] = error.status
                    save_job(root, job)
                    publish_event(root, capacity, job, 'create_ended_without_id')
                    changed.set()
                    return
                job['taskId'] = identifier
                job['timings']['taskId'] = time.perf_counter()
                write_json(receipt_path(root, operation, 'create'), sealed({
                    **{k: job[k] for k in ('operationId', 'projectId', 'requestHash', 'taskId')}, 'receivedAt': now()}))
                options.checkpoint('after-receipt', job)
                job['status'] = 'queued'
                options.checkpoint('before-job-save', job)
                save_job(root, job)
                publish_event(root, capacity, job, 'create_accepted')
        else:
            reconcile_create(root, job)
        if options.submit_only:
            return
        if not job.get('taskId'):
            if job['status'] in ('submitting', 'prepared'):
                job['status'] = 'submit_unknown'
                save_job(root, job)
            return
        existing = await asyncio.to_thread(reconcile_output, root, job)
        if existing:
            job['output'], job['status'] = existing, 'downloaded'
            save_job(root, job)
            return
        if job['status'] == 'downloaded' and job.get('resultUrl'):
            # The remote terminal fact survives a missing local delivery file.
            job['status'] = 'generated'
            save_job(root, job)
        if job['status'] in ('failed', 'cancelled'):
            return
        if job['status'] != 'generated':
            for index in range(options.max_polls):
                state = await observe_once(root, job, capacity, provider, queries or asyncio.Semaphore(4), options, changed)
                if state is None:
                    return
                if state in ('generated', 'downloaded', 'failed', 'cancelled'):
                    break
                if index + 1 < options.max_polls:
                    await asyncio.sleep(options.poll_seconds)
            else:
                job['error'] = {'code': 'POLL_LIMIT', 'message': 'Local query budget ended; remote task may remain active.'}
                save_job(root, job)
                return  # Explicit queued/running remains held.
        if job['status'] == 'generated' and options.download_results:
            await download(root, job, item, provider, downloads, options)
    except asyncio.CancelledError:
        if job['status'] == 'submitting' and not job.get('taskId'):
            job['status'] = 'submit_unknown'
            save_job(root, job)
            publish_event(root, capacity, job, 'create_ended_without_id')
        raise
    except (AppError, OSError) as error:
        job['error'] = {'code': error.code if isinstance(error, AppError) else 'LOCAL_IO',
                        'message': error.message if isinstance(error, AppError) else 'Local I/O failed; preserve task evidence.'}
        save_job(root, job)
    finally:
        changed.set()


async def observe_once(root: Path, job: dict, capacity: Capacity, provider: Metaso,
                       queries: asyncio.Semaphore, options: ExecutionOptions, changed: asyncio.Event) -> str | None:
    """One identified GET and the same durable R3 publication for both scopes."""
    operation = job['operationId']
    async with queries:
        sequence = capacity.issue(operation)
        try:
            observed = await provider.query(job['taskId'], project_path(root, f'{STATE}/receipts/{operation}/query-{sequence}'), operation, job['requestHash'])
            if observed.get('taskId') != job['taskId']:
                raise AppError('QUERY_CONTRACT', 'Query identity mismatch.')
        except (ProviderError, AppError) as error:
            if capacity.read()['slots'][operation]['capacity']['terminal']:
                job.update(load_job(root, operation))
                return job['status']
            job['status'] = 'query_unknown'
            job['error'] = {'code': error.code, 'message': error.message}
            save_job(root, job)
            publish_event(root, capacity, job, 'query_unavailable', sequence)
            changed.set()
            return None
        # Late active/error observations cannot overwrite an already committed terminal.
        if capacity.read()['slots'][operation]['capacity']['terminal']:
            job.update(load_job(root, operation))
            return job['status']
        job['status'] = observed['status']
        terminal = job['status'] in ('generated', 'failed', 'cancelled')
        if terminal:
            job.setdefault('timings', {})['terminal'] = time.perf_counter()
            if observed.get('url'):
                job['resultUrl'] = observed['url']
        save_job(root, job)
        publish_event(root, capacity, job, 'provider_terminal' if terminal else 'remote_active_recovered', sequence)
        if terminal:
            options.checkpoint('after-capacity-event', job)
            changed.set()
        return job['status']


async def observe_history(root: Path, job: dict, capacity: Capacity, provider: Metaso,
                          queries: asyncio.Semaphore, options: ExecutionOptions, changed: asyncio.Event,
                          pending: list, deadline_state: list[float]) -> None:
    try:
        with lock(capacity.root / 'owners' / f'{job["operationId"]}.lock', timeout=0):
            if not deadline_state:
                deadline_state.append(time.monotonic() + options.capacity_wait)
            deadline = deadline_state[0]
            for index in range(options.max_polls):
                # Capacity budget governs additional rounds, not cancellation of accepted GETs.
                if (not pending or options.capacity_wait <= 0
                        or (index > 0 and time.monotonic() >= deadline)):
                    return
                state = await observe_once(root, job, capacity, provider, queries, options, changed)
                if state not in ('queued', 'running') or index + 1 == options.max_polls:
                    return
                # Reuse the caller's poll interval within its existing capacity
                # budget; never start a second long wait for historical work.
                if time.monotonic() + options.poll_seconds >= deadline:
                    return
                await asyncio.sleep(options.poll_seconds)
    except (AppError, OSError):
        # A live operation owner or unavailable local source is not a remote failure.
        return
    finally:
        changed.set()


def delivery(root: Path, plan: dict, run: dict | None, reused_ids: set[str] | None = None) -> dict:
    segments = []
    for index, item in enumerate(plan['segments']):
        binding = run['items'][index] if run else {}
        operation = binding.get('operationId')
        row = {'episodeId': item['episodeId'], 'segmentId': item['segmentId'], 'reused': False, 'status': 'pending'}
        if operation:
            job = load_job(root, operation)
            row.update(operationId=operation, status=job['status'])
            if job.get('taskId'):
                row['taskId'] = job['taskId']
            try:
                output = reconcile_output(root, job)
                if output:
                    row.update(status='downloaded', output={**output, 'absolutePath': str(project_path(root, output['path']))},
                               reused=operation in (reused_ids or set()))
                elif job['status'] == 'downloaded':
                    row['error'] = {'code': 'OUTPUT_NEEDS_RECOVERY', 'message': 'Saved output is missing; recover the original task download.'}
            except AppError as error:
                row['error'] = {'code': error.code, 'message': error.message}
            if job.get('error') and 'error' not in row and row['status'] != 'downloaded':
                row['error'] = job['error']
        segments.append(row)
    complete = all(s['status'] == 'downloaded' and s.get('output') and 'error' not in s for s in segments)
    result = {'schemaVersion': 1, 'batchId': plan['batchId'], 'batchHash': plan['batchHash'], 'scopeHash': plan['scopeHash'],
              'phase': 'complete' if complete else 'partial' if run else 'prepared',
              'reused': complete and all(s['reused'] for s in segments), 'segments': segments}
    write_json(project_path(root, f'{STATE}/batches/{plan["batchId"]}/delivery-v1.json'), sealed(result))
    return result


async def run_video(root: Path, batch_id: str, *, provider: Metaso | None = None,
                    runtime: Path | None = None, confirm: bool = False, resume: bool = False,
                    options: ExecutionOptions | None = None, full_scope: bool = False) -> dict:
    began = time.perf_counter()
    options = options or ExecutionOptions()
    plan = load_plan(root, batch_id)
    runpath = project_path(root, f'{STATE}/batches/{batch_id}/run.json')
    run = verify(read_json(runpath)) if runpath.exists() else None
    if run:
        validate_record(VideoRun, run)
        if run['batchId'] != batch_id or len(run['items']) != len(plan['segments']):
            raise AppError('AUTHORIZATION_IDENTITY', 'Saved run order or identity differs from its plan.')
    if run and run['batchHash'] != plan['batchHash']:
        raise AppError('AUTHORIZATION_IDENTITY', 'Run belongs to another frozen plan.')
    reused = set()
    if run:
        for binding in run['items']:
            if binding.get('operationId'):
                saved_job = load_job(root, binding['operationId'])
                try:
                    if reconcile_output(root, saved_job):
                        reused.add(saved_job['operationId'])
                except AppError:
                    pass
    if not confirm and not resume:
        return delivery(root, plan, run, reused)
    if resume and not run:
        raise AppError('AUTHORIZATION_REQUIRED', 'No original frozen authorization to resume.')
    if provider is None or runtime is None:
        raise AppError('CONFIGURATION_REQUIRED', 'Authenticated provider and runtime are required.')
    if plan['workflow'] not in ('h3-inline-ir', 'h3-context-ir-derived'):
        raise AppError('INLINE_IR_REQUIRED', 'Video submission requires the inline IR workflow.')
    capacity = Capacity(runtime)
    # One story submission engine for image/video, independently from short write locks.
    owner = project_path(root, f'{STATE}/submission.lock')
    with lock(owner, timeout=0):
        if run and run.get('runtimeRoot') != str(runtime.absolute()).casefold():
            raise AppError('RUNTIME_CONFLICT', 'Resume must use the original capacity runtime.')
        capacity.register_existing(root)
        if run is None:
            run = {'schemaVersion': 1, 'batchId': batch_id, 'batchHash': plan['batchHash'],
                   'runtimeRoot': str(runtime.absolute()).casefold(),
                   'authorization': {'batchHash': plan['batchHash'], 'authorizedAt': now()},
                   'items': [{} for _ in plan['segments']]}
            write_json(runpath, sealed(run))
        if run['authorization']['batchHash'] != plan['batchHash']:
            raise AppError('AUTHORIZATION_IDENTITY', 'Authorization hash mismatch.')
        if full_scope and confirm and 'authorizedOrders' in run['authorization']:
            for selected_item in plan['segments']:
                assert_current(root, plan, selected_item)
            authorization_path = project_path(root, f'{STATE}/batches/{batch_id}/full-authorization.json')
            if not authorization_path.exists():
                write_json(authorization_path, sealed({'batchId': batch_id, 'batchHash': plan['batchHash'],
                    'previousAuthorization': run['authorization'], 'authorizedAt': now()}))
            approval = verify(read_json(authorization_path))
            if approval['batchHash'] != plan['batchHash']:
                raise AppError('AUTHORIZATION_IDENTITY', 'Full batch authorization belongs to another plan.')
            run['authorization'].pop('authorizedOrders')
            write_json(runpath, sealed(run))
        jobs = sorted(find_jobs(root), key=lambda j: (j['createdAt'], j['attempt']))
        pending: list[tuple[int, dict, dict | None]] = []
        existing: list[tuple[dict, dict]] = []
        for index, item in enumerate(plan['segments']):
            binding = run['items'][index]
            matches = [j for j in jobs if j['projectId'] == plan['projectId'] and j['episodeId'] == item['episodeId']
                       and j['segmentId'] == item['segmentId'] and j['inputHash'] == item['inputHash']]
            job = load_job(root, binding['operationId']) if binding.get('operationId') else (matches[-1] if matches else None)
            if job:
                if job['inputHash'] != item['inputHash'] or job['episodeId'] != item['episodeId'] or job['segmentId'] != item['segmentId']:
                    raise AppError('JOB_IDENTITY', 'Batch operation binding mismatch.')
                binding['operationId'] = job['operationId']
                try:
                    if reconcile_output(root, job):
                        reused.add(job['operationId'])
                except AppError as error:
                    if error.code not in ('OUTPUT_CHANGED', 'VIDEO_INVALID', 'VIDEO_CHANGED', 'OUTPUT_RECEIPT_MISSING'):
                        raise
                if job['status'] == 'prepared' and job.get('retryOf'):
                    pending.append((index, item, job))
                else:
                    existing.append((item, job))
            else:
                if 'authorizedOrders' not in run['authorization'] or index in run['authorization']['authorizedOrders']:
                    pending.append((index, item, None))
        write_json(runpath, sealed(run))
        ticket = capacity.ticket(root, plan, len(pending), owner)
        downloads = asyncio.Semaphore(2)
        queries = asyncio.Semaphore(4)
        changed = asyncio.Event()
        tasks: set[asyncio.Task] = set()
        created_this_run: set[str] = set()
        for item, job in existing:
            tasks.add(asyncio.create_task(execute_job(root, plan, item, job, capacity, provider, downloads, options, changed, queries=queries)))
        observers = set()
        history_deadline: list[float] = []
        observed_operations: set[str] = set()
        if pending:
            excluded = {j['operationId'] for _, j in existing} | {j['operationId'] for _, _, j in pending if j}
            for _, _, retry in pending:
                ancestor = retry.get('retryOf') if retry else None
                while ancestor:
                    excluded.add(ancestor)
                    ancestor = load_job(root, ancestor).get('retryOf')
            for job in capacity.observation_candidates(root, plan['projectId'], excluded):
                reconcile_create(root, job)
                observed_operations.add(job['operationId'])
                observers.add(asyncio.create_task(observe_history(root, job, capacity, provider, queries, options, changed, pending, history_deadline)))
        wait_start = time.monotonic()
        blocker = None
        # Validate the entire unsubmitted scope before the first new paid action.
        try:
            for _, item, _ in pending:
                assert_current(root, plan, item)
        except AppError as error:
            blocker = {'code': error.code, 'message': error.message}
        try:
            while pending or tasks:
                while pending and blocker is None:
                    index, item, retry_job = pending[0]
                    if retry_job:
                        original = load_job(root, retry_job['retryOf'])
                        reconcile_create(root, original)
                        if original.get('taskId') and retry_job.get('unknownRetry'):
                            retry_job.update(status='cancelled', error={'code': 'RETRY_SUPERSEDED', 'message': 'Original creation receipt recovered before the new attempt.'})
                            save_job(root, retry_job)
                            run['items'][index]['operationId'] = original['operationId']
                            write_json(runpath, sealed(run))
                            pending.pop(0)
                            capacity.update_ticket(ticket, len(pending))
                            tasks.add(asyncio.create_task(execute_job(root, plan, item, original, capacity, provider, downloads, options, changed, queries=queries)))
                            continue
                    from ..application.stages import new_submission
                    accepted = {j['operationId'] for _, j in existing if j.get('taskId')}
                    accepted.update(observed_operations)
                    current_jobs = find_jobs(root)
                    accepted.update(t['operationId'] for t in current_jobs if t['status'] == 'submitting' and t.get('planId') == batch_id)
                    slots = capacity.read()['slots']
                    for prior_job in current_jobs:
                        same_input = all(prior_job[k] == item[k] for k in ('episodeId', 'segmentId', 'inputHash'))
                        if not same_input and slots.get(prior_job['operationId'], {}).get('capacity', {}).get('state') == 'released':
                            accepted.add(prior_job['operationId'])
                    ancestor = retry_job.get('retryOf') if retry_job else None
                    while ancestor:
                        accepted.add(ancestor)
                        ancestor = load_job(root, ancestor).get('retryOf')
                    try:
                        new_submission(root, 'video', accepted)
                        assert_current(root, plan, item)
                        if any(j.get('error', {}).get('httpStatus') in (401, 402, 403)
                               for j in current_jobs if j['operationId'] in created_this_run):
                            raise AppError('PROVIDER_AUTHORIZATION', 'Provider authentication or quota rejected; no additional creates started.')
                    except AppError as error:
                        blocker = {'code': error.code, 'message': error.message}
                        break
                    operation = retry_job['operationId'] if retry_job else str(uuid.uuid4())
                    job = retry_job or {'schemaVersion': 1, 'operationId': operation, 'projectId': plan['projectId'],
                           'planId': batch_id, 'planHash': plan['batchHash'], 'episodeId': item['episodeId'],
                           'segmentId': item['segmentId'], 'requestHash': item['requestHash'], 'inputHash': item['inputHash'],
                           'status': 'prepared', 'attempt': 1, 'createdAt': now(), 'timings': {'prepared': time.perf_counter()}}
                    operation_owner = capacity.root / 'owners' / f'{operation}.lock'
                    lease = ExitStack()
                    lease.enter_context(lock(operation_owner, timeout=0))
                    try:
                        if not capacity.reserve(ticket, job, root, operation_owner):
                            lease.close()
                            break
                        save_job(root, job)
                        run['items'][index]['operationId'] = operation
                        write_json(runpath, sealed(run))
                    except BaseException:
                        lease.close()
                        raise
                    pending.pop(0)
                    capacity.update_ticket(ticket, len(pending))
                    created_this_run.add(operation)
                    tasks.add(asyncio.create_task(execute_job(root, plan, item, job, capacity, provider, downloads, options, changed, submit=True, owner_lease=lease, queries=queries)))
                    wait_start = time.monotonic()
                    await asyncio.sleep(0)
                done = {task for task in tasks if task.done()}
                for task in done:
                    task.result()
                tasks -= done
                if blocker is not None and not tasks:
                    break
                if not tasks and pending and all(t.done() for t in observers) and time.monotonic() - wait_start >= options.capacity_wait:
                    break
                if not tasks and not pending:
                    break
                changed.clear()
                try:
                    await asyncio.wait_for(changed.wait(), options.capacity_poll)
                except TimeoutError:
                    pass
        finally:
            for observer in observers:
                observer.cancel()
            await asyncio.gather(*observers, return_exceptions=True)
            capacity.update_ticket(ticket, 0)
            if tasks:
                # Stop new dispatch, give receipt writers bounded time, then persist
                # unknowns on cancellation. Never infer remote cancellation.
                done, still = await asyncio.wait(tasks, timeout=min(5, options.capacity_wait))
                for task in still:
                    task.cancel()
                await asyncio.gather(*still, return_exceptions=True)
        delivery_began = time.perf_counter()
        result = delivery(root, plan, run, reused)
        if blocker is not None:
            result['blocker'] = blocker
        result['timings'] = {'executeMs': (time.perf_counter()-began)*1000,
                             'deliveryMs': (time.perf_counter()-delivery_began)*1000}
        result['capacity'] = {s['operationId']: s['capacity'] for s in capacity.read()['slots'].values() if s['projectId'] == plan['projectId']}
        return result
