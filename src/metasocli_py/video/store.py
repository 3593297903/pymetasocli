from pathlib import Path

from ..application.story import STATE, load_story
from ..contracts.records import VideoJob, validate_record
from ..domain.errors import AppError
from ..persistence.codec import sealed, verify
from ..persistence.files import lock, project_path, read_json, write_json


def save_job(root: Path, job: dict) -> None:
    from .planning import now
    proposed = {**job, 'recordVersion': job.get('recordVersion', 0) + 1, 'updatedAt': now()}
    path = project_path(root, f'{STATE}/jobs/{job["operationId"]}.json')
    with lock(project_path(root, f'{STATE}/story.lock')):
        if path.exists():
            current = verify(read_json(path))
            if current['recordVersion'] != proposed['recordVersion'] - 1:
                raise AppError('JOB_STALE', 'Concurrent task update; recover the current record.')
        saved = sealed(proposed)
        validate_record(VideoJob, saved)
        write_json(path, saved)
        job.update(proposed)


def load_job(root: Path, operation: str, *, validate_parent: bool = True) -> dict:
    job = validate_record(VideoJob, verify(read_json(project_path(root, f'{STATE}/jobs/{operation}.json'))))
    if job['operationId'] != operation or job['projectId'] != load_story(root)['projectId']:
        raise AppError('JOB_IDENTITY', 'Job belongs to another story or operation filename.')
    if validate_parent:
        from .planning import load_plan
        plan = load_plan(root, job['planId'])
        item = next((s for s in plan['segments'] if s['episodeId'] == job['episodeId'] and s['segmentId'] == job['segmentId']), None)
        if plan['batchHash'] != job['planHash'] or item is None or any(item[k] != job[k] for k in ('requestHash', 'inputHash')):
            raise AppError('JOB_IDENTITY', 'Job differs from its immutable parent plan.')
    if job['status'] in ('queued', 'running', 'generated', 'downloaded', 'query_unknown') and not job.get('taskId'):
        raise AppError('JOB_IDENTITY', 'Accepted task state is missing its remote identity.')
    return job


def find_jobs(root: Path) -> list[dict]:
    folder = project_path(root, f'{STATE}/jobs')
    return [load_job(root, path.stem, validate_parent=False) for path in sorted(folder.glob('*.json'))] if folder.exists() else []
