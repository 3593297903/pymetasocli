"""R3 capacity ledger. No network or story writes occur under its short lock."""
import copy
import os
import uuid
from pathlib import Path

from ..domain.errors import AppError
from ..persistence.codec import digest, sealed, sha256, verify
from ..persistence.files import is_locked, lock, project_path, read_json, read_stable, safe_path, write_json
from .planning import now

ACTIVE_REASONS = {'reserved', 'create_accepted', 'remote_active_recovered'}
REASONS = ACTIVE_REASONS | {'create_ended_without_id', 'submitter_exited_without_id', 'query_unavailable', 'source_unavailable', 'provider_terminal'}


def root_key(root: Path) -> str:
    return os.path.normcase(str(safe_path(root)))


def apply_decision(slot: dict, event: dict) -> bool:
    """Identity + logical observation clocks, with irreversible trusted terminal facts."""
    for key in ('operationId', 'projectId', 'requestHash'):
        if event[key] != slot[key]:
            raise AppError('CAPACITY_IDENTITY', 'Capacity event identity mismatch.')
    if event['reason'] not in REASONS or type(event['sequence']) is not int or event['sequence'] < 0:
        raise AppError('CAPACITY_EVENT', 'Invalid capacity observation.')
    old = slot['capacity']
    identifier = event.get('taskId')
    if identifier is not None and slot.get('taskId') not in (None, identifier):
        raise AppError('CAPACITY_IDENTITY', 'Capacity task ID conflict.')
    terminal = event['reason'] == 'provider_terminal'
    if terminal and not identifier:
        raise AppError('CAPACITY_IDENTITY', 'Terminal evidence requires an identified task.')
    if old['terminal']:
        return False
    if not terminal and (event['sequence'] <= old['applied'] or event['sequence'] != old['issued']):
        return False
    if slot.get('taskId') and not identifier and event['reason'] in ('create_ended_without_id', 'submitter_exited_without_id'):
        old['applied'] = max(old['applied'], event['sequence'])
        return True
    state = 'held' if event['reason'] in ACTIVE_REASONS else 'released'
    new = {**old, 'version': old['version']+1, 'state': state, 'reason': event['reason'],
           'evidence': digest(event), 'decidedAt': now(), 'terminal': terminal,
           'issued': max(old['issued'], event['sequence']), 'applied': max(old['applied'], event['sequence'])}
    basis = {k: new[k] for k in ('version', 'reason', 'evidence', 'decidedAt')}
    if event.get('sourceEvidence'):
        basis['sourceEvidence'] = event['sourceEvidence']
    if state == 'released':
        new['lastRelease'] = basis
    elif old['state'] == 'released':
        new['lastRestore'] = basis
    slot['capacity'] = new
    if identifier:
        slot['taskId'] = identifier
    return True


class Capacity:
    def __init__(self, runtime: Path):
        self.root = safe_path(runtime)
        self.file = self.root / 'video-ledger.json'
        self.lockfile = self.root / 'video-ledger.lock'

    def read(self) -> dict:
        marker = self.root / 'video-owner.json'
        if not self.file.exists():
            if marker.exists():
                raise AppError('LEDGER_MISSING', 'Capacity ledger is missing from an initialized runtime; preserve evidence.')
            return {'schemaVersion': 1, 'slots': {}, 'tickets': []}
        if not marker.exists() or read_json(marker) != {'owner': 'metasocli-py', 'schemaVersion': 1}:
            raise AppError('LEDGER_OWNER', 'Shared capacity owner marker is missing or invalid.')
        record = verify(read_json(self.file))
        from ..contracts.records import Ledger, validate_record
        validate_record(Ledger, record)
        if record.get('schemaVersion') != 1 or not isinstance(record.get('slots'), dict) or not isinstance(record.get('tickets'), list):
            raise AppError('LEDGER_CORRUPT', 'Invalid shared capacity ledger; preserve evidence.')
        for key, slot in record['slots'].items():
            if slot.get('operationId') != key or slot.get('capacity', {}).get('state') not in ('held', 'released'):
                raise AppError('LEDGER_CORRUPT', 'Invalid capacity slot.')
        identifiers = [s['taskId'] for s in record['slots'].values() if s.get('taskId')]
        if len(identifiers) != len(set(identifiers)):
            raise AppError('TASK_LINK_CONFLICT', 'Remote task ID is duplicated across registered operations.')
        roots: dict[str, str] = {}
        projects: dict[str, str] = {}
        for entry in [*record['slots'].values(), *record['tickets']]:
            root, project = entry['root'], entry['projectId']
            if roots.get(root, project) != project or projects.get(project, root) != root:
                raise AppError('CAPACITY_IDENTITY', 'Capacity project and directory bindings must be one-to-one.')
            roots[root], projects[project] = project, root
        return record

    def save(self, record: dict) -> None:
        marker = self.root / 'video-owner.json'
        if not marker.exists():
            write_json(marker, {'owner': 'metasocli-py', 'schemaVersion': 1})
        write_json(self.file, sealed({k: v for k, v in record.items() if k not in ('hash', 'hashVersion')}))

    def register_existing(self, root: Path) -> dict:
        from .store import find_jobs
        jobs = find_jobs(root)
        with lock(self.lockfile):
            record = self.read()
            for job in jobs:
                previous = record['slots'].get(job['operationId'])
                if previous:
                    if previous['root'] != root_key(root) or any(previous[k] != job[k] for k in ('projectId', 'requestHash', 'inputHash')):
                        raise AppError('CAPACITY_IDENTITY', 'Existing capacity registration conflicts with this story.')
                    continue
                if job['status'] == 'prepared':
                    continue
                terminal = bool(job.get('taskId')) and job['status'] in ('generated', 'downloaded', 'failed', 'cancelled')
                held = bool(job.get('taskId')) and not terminal
                record['slots'][job['operationId']] = {
                    **{k: job[k] for k in ('operationId', 'projectId', 'requestHash', 'inputHash')},
                    'root': root_key(root), 'owner': str(project_path(root, '.metasocli-py/submission.lock')),
                    **({'taskId': job['taskId']} if job.get('taskId') else {}),
                    'capacity': {'policy': 'R3', 'state': 'held' if held else 'released',
                        'reason': 'provider_terminal' if terminal else 'create_accepted' if held else 'create_ended_without_id',
                        'version': 0, 'issued': 0, 'applied': 0, 'terminal': terminal,
                        'evidence': job['hash'], 'decidedAt': now()}}
            self.save(record)
        self.audit()
        current = self.read()
        return {'registeredOperations': len(jobs), 'occupied': sum(s['capacity']['state'] == 'held' for s in current['slots'].values()),
                'limit': 4, 'liveCheckPerformed': False}

    def ticket(self, root: Path, plan: dict, remaining: int, owner: Path) -> str:
        ticket_id = str(uuid.uuid4())
        with lock(self.lockfile):
            record = self.read()
            if any((s['projectId'] == plan['projectId']) != (s['root'] == root_key(root)) for s in [*record['slots'].values(), *record['tickets']]):
                raise AppError('CAPACITY_IDENTITY', 'Project identity is already registered at another directory.')
            record['tickets'].append({'ticketId': ticket_id, 'root': root_key(root), 'projectId': plan['projectId'],
                'batchId': plan['batchId'], 'scopeHash': plan['scopeHash'], 'limit': plan['concurrency'],
                'remaining': remaining, 'owner': str(owner), 'enteredAt': now()})
            self.save(record)
        return ticket_id

    def observation_candidates(self, root: Path, project: str, excluded: set[str]) -> list[dict]:
        """Read only: the run's story lease is not a historical operation owner."""
        from .store import load_job
        with lock(self.lockfile):
            slots = list(self.read()['slots'].values())
        jobs = []
        for slot in slots:
            operation = slot['operationId']
            if (operation in excluded or slot['root'] != root_key(root) or slot['projectId'] != project
                or slot['capacity']['state'] != 'held' or slot['capacity']['terminal'] or not slot.get('taskId')
                or is_locked(self.root / 'owners' / f'{operation}.lock')):
                continue
            job = load_job(root, operation)
            if (any(job.get(k) != slot.get(k) for k in ('operationId', 'projectId', 'requestHash', 'inputHash'))
                or job.get('taskId') not in (None, slot['taskId'])):
                raise AppError('CAPACITY_IDENTITY', 'Historical observation identity mismatch.')
            if not job.get('taskId'):
                receipt = verify(read_json(project_path(root, f'.metasocli-py/receipts/{operation}-create.json')))
                if any(receipt.get(k) != slot.get(k) for k in ('operationId', 'projectId', 'requestHash', 'taskId')):
                    raise AppError('CAPACITY_IDENTITY', 'Historical creation receipt identity mismatch.')
            jobs.append(job)
        return jobs

    def update_ticket(self, ticket_id: str, remaining: int) -> None:
        with lock(self.lockfile):
            record = self.read()
            record['tickets'] = [dict(t, remaining=remaining) if t['ticketId'] == ticket_id else t
                                 for t in record['tickets'] if t['ticketId'] != ticket_id or remaining > 0]
            self.save(record)

    def reserve(self, ticket_id: str, job: dict, root: Path, owner: Path) -> bool:
        with lock(self.lockfile):
            record = self.read()
            # OS owner lock is the authority. Metadata timestamps are never leases.
            tickets = [t for t in record['tickets'] if t['remaining'] > 0 and is_locked(safe_path(t['owner']))]
            record['tickets'] = tickets
            held = [s for s in record['slots'].values() if s['capacity']['state'] == 'held']
            free = max(0, 4-len(held))
            shares: dict[str, int] = {}
            allowed = False
            earlier_ready = False
            for ticket in tickets:
                occupied = sum(s['root'] == ticket['root'] for s in held)
                need = min(ticket['remaining'], max(0, ticket['limit']-occupied-shares.get(ticket['root'], 0)))
                share = min(free, need)
                shares[ticket['root']] = shares.get(ticket['root'], 0) + share
                free -= share
                if ticket['ticketId'] == ticket_id:
                    allowed = share > 0 and not earlier_ready
                elif not allowed and share > 0:
                    earlier_ready = True
            if not allowed:
                self.save(record)
                return False
            operation = job['operationId']
            if operation in record['slots']:
                raise AppError('OPERATION_EXISTS', 'Reservation already exists; recover its operation.')
            stamp = now()
            record['slots'][operation] = {'operationId': operation, 'projectId': job['projectId'],
                'root': root_key(root), 'requestHash': job['requestHash'], 'inputHash': job['inputHash'],
                'owner': str(owner), 'capacity': {'policy': 'R3', 'state': 'held', 'reason': 'reserved',
                    'version': 0, 'issued': 0, 'applied': 0, 'terminal': False,
                    'evidence': digest({'operationId': operation}), 'decidedAt': stamp}}
            self.save(record)
            return True

    def issue(self, operation: str) -> int:
        with lock(self.lockfile):
            record = self.read()
            decision = record['slots'][operation]['capacity']
            decision['issued'] += 1
            sequence = decision['issued']
            self.save(record)
            return sequence

    def apply(self, event: dict) -> bool:
        with lock(self.lockfile):
            record = self.read()
            slot = record['slots'].get(event['operationId'])
            if slot is None:
                raise AppError('CAPACITY_MISSING', 'Operation has no shared capacity reservation.')
            if event.get('taskId') and any(s['operationId'] != slot['operationId'] and s.get('taskId') == event['taskId'] for s in record['slots'].values()):
                raise AppError('TASK_LINK_CONFLICT', 'Task ID is already registered to another operation.')
            changed = apply_decision(slot, event)
            if changed:
                self.save(record)
            return changed

    def audit(self) -> None:
        # Capture under runtime lock; all source inspection happens after release.
        with lock(self.lockfile):
            snapshot = copy.deepcopy(self.read())
        for slot in snapshot['slots'].values():
            cap = slot['capacity']
            if cap['terminal'] or (cap['state'] == 'released' and cap['issued'] <= cap['applied'] and slot.get('taskId')):
                continue
            source_evidence = None
            try:
                # A live submitter is protected before looking at incomplete or
                # temporarily unavailable receipt/job files.
                if is_locked(safe_path(slot['owner'])):
                    continue
                root = safe_path(slot['root'])
                eventfile = project_path(root, f'.metasocli-py/receipts/{slot["operationId"]}-capacity.json')
                if eventfile.exists():
                    event = verify(read_json(eventfile))
                    self.apply(event)
                receiptfile = project_path(root, f'.metasocli-py/receipts/{slot["operationId"]}-create.json')
                receipt = verify(read_json(receiptfile)) if receiptfile.exists() else None
                if receipt:
                    for key in ('operationId', 'projectId', 'requestHash'):
                        if receipt[key] != slot[key]:
                            raise AppError('CAPACITY_IDENTITY', 'Create receipt identity mismatch.')
                    if not slot.get('taskId'):
                        self.apply_audit(slot, 'create_accepted', receipt['taskId'])
                        continue
                if not slot.get('taskId') and not is_locked(safe_path(slot['owner'])):
                    reason = 'submitter_exited_without_id'
                elif slot.get('taskId'):
                    job = verify(read_json(project_path(root, f'.metasocli-py/jobs/{slot["operationId"]}.json')))
                    if job.get('taskId') != slot['taskId'] or job.get('requestHash') != slot['requestHash']:
                        raise AppError('CAPACITY_IDENTITY', 'Source job identity mismatch.')
                    if job['status'] in ('generated', 'downloaded', 'failed', 'cancelled'):
                        reason = 'provider_terminal'
                    else:
                        continue
                else:
                    continue
            except (AppError, OSError, KeyError):
                reason = 'source_unavailable'
                fingerprints = []
                for relative in (f'.metasocli-py/jobs/{slot["operationId"]}.json', f'.metasocli-py/receipts/{slot["operationId"]}-create.json'):
                    try:
                        fingerprints.append(sha256(read_stable(project_path(Path(slot['root']), relative), 8*1024*1024)))
                    except (AppError, OSError) as error:
                        fingerprints.append(error.code if isinstance(error, AppError) else type(error).__name__)
                source_evidence = digest(fingerprints)
            self.apply_audit(slot, reason, slot.get('taskId'), source_evidence)

    def apply_audit(self, snapshot: dict, reason: str, identifier: str | None, source_evidence: str | None = None) -> None:
        with lock(self.lockfile):
            record = self.read()
            slot = record['slots'][snapshot['operationId']]
            if slot != snapshot or slot['capacity']['terminal'] or is_locked(safe_path(slot['owner'])):
                return
            cap = slot['capacity']
            if source_evidence and cap.get('lastRelease', {}).get('sourceEvidence') == source_evidence and cap.get('lastRestore', {}).get('version', -1) > cap['lastRelease']['version']:
                return
            if identifier and any(s['operationId'] != slot['operationId'] and s.get('taskId') == identifier for s in record['slots'].values()):
                raise AppError('TASK_LINK_CONFLICT', 'Recovered ID already belongs to another operation.')
            slot['capacity']['issued'] += 1
            event = {**{k: slot[k] for k in ('operationId', 'projectId', 'requestHash')},
                'sequence': slot['capacity']['issued'], 'reason': reason, **({'taskId': identifier} if identifier else {}),
                **({'sourceEvidence': source_evidence} if source_evidence else {})}
            apply_decision(slot, event)
            self.save(record)
