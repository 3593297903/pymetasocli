import uuid
from pathlib import Path

from ..application.story import STATE
from ..domain.errors import AppError
from ..persistence.codec import sealed, verify
from ..persistence.files import lock, project_path, read_json, write_json
from .planning import load_plan, now
from .store import find_jobs, load_job, save_job


def authorize_retry(root: Path, batch_id: str, operation: str, confirm: bool, accept_unknown: bool) -> dict:
    if not confirm:
        raise AppError('AUTHORIZATION_REQUIRED', 'One new attempt requires explicit confirmation.')
    plan = load_plan(root, batch_id)
    with lock(project_path(root, f'{STATE}/submission.lock'), timeout=0):
        old = load_job(root, operation)
        index = next((i for i, s in enumerate(plan['segments']) if s['episodeId'] == old['episodeId'] and s['segmentId'] == old['segmentId'] and s['inputHash'] == old['inputHash']), None)
        if index is None:
            raise AppError('RETRY_IDENTITY', 'Old attempt is outside this frozen scope.')
        # A recovered failure uses a distinct explicit grant; never revive the
        # earlier, now obsolete, unknown-result grant.
        suffix = '-known-failure' if old.get('taskId') and not accept_unknown else ''
        authfile = project_path(root, f'{STATE}/retries/{operation}{suffix}.json')
        if authfile.exists():
            authorization = verify(read_json(authfile))
            if authorization['batchId'] != batch_id or authorization['oldOperationId'] != operation:
                raise AppError('RETRY_ALREADY_AUTHORIZED', 'A different retry is already authorized.')
        else:
            if old['status'] not in ('submit_unknown', 'failed', 'cancelled'):
                raise AppError('RETRY_NOT_ALLOWED', 'Recover accepted/active tasks using the original task ID.')
            if old['status'] == 'submit_unknown' and (old.get('taskId') or not accept_unknown):
                raise AppError('UNKNOWN_ACCEPTANCE_REQUIRED', 'Unknown retry requires no task ID and explicit acceptance.')
            peers = [j for j in find_jobs(root) if j['episodeId'] == old['episodeId'] and j['segmentId'] == old['segmentId']]
            effective = [j for j in peers if j.get('error', {}).get('code') != 'RETRY_SUPERSEDED']
            if any(j['operationId'] != operation and j['attempt'] >= old['attempt'] for j in effective):
                raise AppError('RETRY_NOT_LATEST', 'Recover the newer attempt before authorizing another.')
            authorization = sealed({'oldOperationId': operation, 'newOperationId': str(uuid.uuid4()),
                'batchId': batch_id, 'batchHash': plan['batchHash'], 'projectId': plan['projectId'],
                'maxNewAttempts': 1, 'acceptUnknown': accept_unknown, 'authorizedAt': now(),
                'attempt': max((j['attempt'] for j in peers), default=0)+1})
            write_json(authfile, authorization)
        successor = authorization['newOperationId']
        successor_file = project_path(root, f'{STATE}/jobs/{successor}.json')
        if successor_file.exists() and load_job(root, successor).get('error', {}).get('code') == 'RETRY_SUPERSEDED':
            # An old grant remains inspectable/idempotent but must not steal the
            # run binding from the recovered original or a newer explicit retry.
            return authorization
        if not successor_file.exists():
            receipts = project_path(root, f'{STATE}/receipts')
            if any(receipts.glob(successor + '*')):
                raise AppError('RETRY_EVIDENCE_CONFLICT', 'Missing retry job has durable submission evidence; restore it without sending.')
            new = {k: old[k] for k in ('schemaVersion', 'projectId', 'episodeId', 'segmentId', 'requestHash', 'inputHash')}
            new.update(operationId=successor, planId=batch_id, planHash=plan['batchHash'], retryOf=operation,
                       attempt=authorization['attempt'], status='prepared', createdAt=now(), timings={}, unknownRetry=authorization['acceptUnknown'])
            save_job(root, new)
        runfile = project_path(root, f'{STATE}/batches/{batch_id}/run.json')
        original_run = verify(read_json(project_path(root, f'{STATE}/batches/{old["planId"]}/run.json')))
        run = verify(read_json(runfile)) if runfile.exists() else {
            'schemaVersion': 1, 'batchId': batch_id, 'batchHash': plan['batchHash'],
            'runtimeRoot': original_run['runtimeRoot'],
            'authorization': {'batchHash': plan['batchHash'], 'authorizedAt': now(), 'authorizedOrders': [index]},
            'items': [{} for _ in plan['segments']]}
        current = run['items'][index].get('operationId')
        if current and current != successor and load_job(root, current)['attempt'] > authorization['attempt']:
            return authorization
        run['items'][index] = {'operationId': successor, 'retryOf': operation}
        write_json(runfile, sealed(run))
        return authorization
