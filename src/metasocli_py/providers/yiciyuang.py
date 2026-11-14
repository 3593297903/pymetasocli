from contextlib import ExitStack
from pathlib import Path

from ..domain.errors import AppError
from ..images.contracts import timeout_seconds
from ..persistence.codec import sha256
from ..persistence.files import project_path, read_stable
from .http import IMAGE_ORIGIN, Http, save_complete


class Yiciyuang:
    def __init__(self, http: Http, key: str, *, test_timeout: float | None = None):
        if not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise AppError('IMAGE_KEY_INVALID', 'Configure the independent image credential.')
        self.http, self.key = http, key
        if test_timeout is not None and http.loopback_origin is None:
            raise AppError('TEST_ENDPOINT', 'Short test deadlines require explicit loopback injection.')
        self.test_timeout = test_timeout

    async def create(self, root: Path, job: dict, profile: dict, folder: Path) -> dict:
        request = job['input']
        prompt = read_stable(project_path(root, request['promptPath']), 128000)
        if sha256(prompt) != request['promptHash']:
            raise AppError('IMAGE_INPUT_CHANGED', 'Frozen prompt changed.')
        fields = {k: request[k] for k in ('model', 'quality', 'size', 'n', 'response_format')}
        fields['prompt'] = prompt.decode('utf-8')
        references = request['references']
        headers = {'Authorization': 'Bearer ' + self.key}
        with ExitStack() as handles:
            files = []
            for reference in references:
                file = project_path(root, reference['path'])
                if sha256(read_stable(file, profile['maxImageBytes'])) != reference['sha256']:
                    raise AppError('IMAGE_INPUT_CHANGED', 'Frozen reference changed.')
                stream = handles.enter_context(file.open('rb'))
                ext = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}[reference['mime']]
                files.append(('image' if len(references) == 1 else 'image[]',
                              (reference['assetId'] + ext, stream, reference['mime'])))
            meta = await self.http.stream('POST', self.http.api(IMAGE_ORIGIN, request['route']), folder / 'response.bin',
                total=self.test_timeout or timeout_seconds(profile), limit=profile['maxResponseBytes'], headers=headers,
                json_body=None if files else fields, data={k: str(v) for k, v in fields.items()} if files else None,
                files=files or None)
        return save_complete(folder, meta, job['operationId'], job['requestHash'])
