import re
from pathlib import Path

from ..domain.errors import AppError
from ..persistence.codec import loads
from ..persistence.files import read_stable
from .http import VIDEO_ORIGIN, Http, ProviderError, save_complete

API = '/api/minimax/v2'


def task_id(value) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', value):
        raise AppError('TASK_ID_INVALID', 'Task identifier must be a bounded string.')
    return value


def extract_id(raw: dict, *, ir: bool = False) -> str:
    if not isinstance(raw, dict):
        raise ProviderError('CREATE_CONTRACT', 'Invalid creation object; do not resubmit.')
    nested = raw.get('task', {})
    if not isinstance(nested, dict):
        raise ProviderError('CREATE_CONTRACT', 'Invalid task object; do not resubmit.')
    expected = 'h3_context_ir' if ir else 'generation'
    for metadata in (raw, nested):
        if metadata.get('model', 'MiniMax-H3') != 'MiniMax-H3' or metadata.get('task_type', expected) != expected:
            raise ProviderError('CREATE_CONTRACT', 'Creation receipt has incompatible task identity; do not resubmit.')
    ids = [task_id(v) for v in (raw.get('task_id'), nested.get('id'), nested.get('task_id')) if v is not None]
    if not ids or len(set(ids)) != 1:
        raise ProviderError('CREATE_CONTRACT', 'Missing or conflicting task ID; do not resubmit.')
    return ids[0]


class Metaso:
    def __init__(self, http: Http, key: str, *, create_timeout: float = 120, query_timeout: float = 30):
        if not key or re.search(r'\s', key):
            raise AppError('API_KEY_MISSING', 'Configure the independent Metaso credential.')
        self.http, self.key = http, key
        self.create_timeout, self.query_timeout = create_timeout, query_timeout

    async def request(self, method: str, route: str, folder: Path, operation_id: str,
                      request_hash: str, body=None) -> dict:
        folder.mkdir(parents=True, exist_ok=True)
        meta = await self.http.stream(method, self.http.api(VIDEO_ORIGIN, API + route), folder / 'response.bin',
            total=self.create_timeout if method == 'POST' else self.query_timeout,
            limit=1024 * 1024, headers={'Authorization': 'Bearer ' + self.key, 'Accept': 'application/json'}, json_body=body)
        save_complete(folder, meta, operation_id, request_hash)
        try:
            raw = loads(read_stable(folder / 'response.bin'))
        except AppError:
            raise ProviderError('PROVIDER_CONTRACT', 'Malformed response preserved.', status=meta['httpStatus']) from None
        if not isinstance(raw, dict):
            raise ProviderError('PROVIDER_CONTRACT', 'Expected an object response.')
        if not 200 <= meta['httpStatus'] < 300:
            def has_id(value):
                return isinstance(value, dict) and any(k in ('id', 'task_id', 'taskId') or has_id(v) for k, v in value.items())
            rejected = not has_id(raw) and meta['httpStatus'] in (400, 401, 402, 403, 404, 422, 429)
            raise ProviderError('PROVIDER_HTTP', f'Provider returned HTTP {meta["httpStatus"]}.',
                                status=meta['httpStatus'], rejected=rejected)
        return raw

    async def create(self, request: dict, folder: Path, operation_id: str, request_hash: str, *, ir=False) -> str:
        raw = await self.request('POST', '/h3_context_ir' if ir else '/video_generation', folder, operation_id, request_hash, request)
        return extract_id(raw, ir=ir)

    async def query(self, identifier: str, folder: Path, operation_id: str, request_hash: str, *, ir=False) -> dict:
        identifier = task_id(identifier)
        raw = await self.request('GET', '/query/video_generation/' + identifier, folder, operation_id, request_hash)
        task = raw.get('task', raw)
        if not isinstance(task, dict) or not isinstance(task.get('status'), str):
            raise ProviderError('QUERY_CONTRACT', 'Unrecognized query response.')
        ids = [task_id(task[k]) for k in ('id', 'task_id') if k in task]
        if not ids or any(i != identifier for i in ids) or task.get('model', 'MiniMax-H3') != 'MiniMax-H3':
            raise ProviderError('QUERY_CONTRACT', 'Query identity/model mismatch.')
        content = task.get('content') or {}
        if not isinstance(content, dict):
            raise ProviderError('QUERY_CONTRACT', 'Invalid task content.')
        if ir:
            if task.get('model') != 'MiniMax-H3' or task.get('task_type') != 'h3_context_ir' or task.get('modality', 'text') != 'text' or 'url' in content:
                raise ProviderError('IR_QUERY_CONTRACT', 'Expected an identified IR text task.')
        elif task.get('task_type', 'generation') != 'generation' or task.get('modality', 'video') != 'video' or 'prompt' in content:
            raise ProviderError('QUERY_CONTRACT', 'Expected a video generation task.')
        status = {'queued': 'queued', 'running': 'running', 'processing': 'running', 'succeeded': 'generated',
            'success': 'generated', 'completed': 'generated', 'failed': 'failed', 'failure': 'failed', 'cancelled': 'cancelled'}.get(task['status'].lower())
        if status is None:
            raise ProviderError('QUERY_CONTRACT', 'Unrecognized remote status.')
        result: dict = {'taskId': identifier, 'status': status}
        if status == 'generated':
            if ir:
                if not isinstance(content.get('prompt'), str) or not content['prompt'].strip():
                    raise ProviderError('IR_QUERY_CONTRACT', 'IR success lacks text.')
                result['prompt'] = content['prompt']
            else:
                result['url'] = content.get('url')
        return result
