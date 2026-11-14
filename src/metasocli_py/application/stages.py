"""Durable same-story barriers, separate from shared-account capacity."""
from pathlib import Path

from ..domain.errors import AppError
from ..persistence.codec import verify
from ..persistence.files import project_path, read_json
from .story import STATE


def assert_task_available(root: Path, identifier: str, operation: str) -> None:
    paths = list(project_path(root, f'{STATE}/jobs').glob('*.json'))
    paths += list(project_path(root, f'{STATE}/context-ir').glob('*/operation.json'))
    for path in paths:
        record = verify(read_json(path))
        if record['operationId'] != operation and record.get('taskId') == identifier:
            raise AppError('TASK_LINK_CONFLICT', 'Task ID is already bound to another operation.')


def new_submission(root: Path, kind: str, accepted: set[str] | None = None) -> None:
    accepted = accepted or set()
    for category, own_kind in [('image-jobs', 'images'), ('jobs', 'video')]:
        folder = project_path(root, f'{STATE}/{category}')
        for path in folder.glob('*.json') if folder.exists() else []:
            job = verify(read_json(path))
            if own_kind == 'video':
                from ..video.store import load_job
                job = load_job(root, path.stem)
            else:
                from ..contracts.records import validate_record
                from ..images.contracts import ImageJob
                validate_record(ImageJob, job)
            if job['operationId'] in accepted:
                continue
            state = job['status']
            unknown = state in ('submitting', 'submit_unknown', 'query_unknown')
            active = state in ('queued', 'running', 'response_saved', 'received', 'downloaded' if own_kind == 'images' else 'generated')
            if unknown or (kind != own_kind and active):
                raise AppError('STAGE_UNRESOLVED', 'Resolve or explicitly authorize the same-story unresolved operation before new submission.')
    folder = project_path(root, f'{STATE}/context-ir')
    if kind != 'ir':
        for path in folder.glob('*/operation.json') if folder.exists() else []:
            if verify(read_json(path))['status'] in ('submitting', 'submit_unknown', 'query_unknown', 'queued', 'running'):
                raise AppError('STAGE_UNRESOLVED', 'Resolve same-story independent IR before new submission.')
