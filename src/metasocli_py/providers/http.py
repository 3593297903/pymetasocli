import asyncio
import hashlib
import ipaddress
import os
import socket
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from ..domain.errors import AppError
from ..persistence.codec import sealed
from ..persistence.files import replace_file, safe_path, write_json

VIDEO_ORIGIN = 'https://metaso.cn'
IMAGE_ORIGIN = 'https://api.yiciyuang.com'


def public_https(url: str, *, resolve: bool = False) -> str:
    try:
        parts = urlsplit(url)
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.fragment or parts.port not in (None, 443):
            raise ValueError
        host = parts.hostname.rstrip('.').lower()
        if host in ('localhost',) or host.endswith(('.localhost', '.local', '.internal')):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError
        if resolve:
            addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
                raise ValueError
        return url
    except (ValueError, OSError):
        raise AppError('URL_UNSAFE', 'Expected a verified public HTTPS media URL.') from None


class ProviderError(AppError):
    def __init__(self, code: str, message: str, *, status: int | None = None, rejected: bool = False):
        super().__init__(code, message, incomplete=True)
        self.status = status
        self.rejected = rejected


class Http:
    def __init__(self, *, mode: str = 'direct', proxy: str | None = None,
                 loopback_origin: str | None = None):
        # loopback_origin is a code-injected testing capability. No CLI/config/env
        # field can select it or alter the fixed production API origins.
        if mode not in ('direct', 'proxy', 'environment') or (mode == 'proxy') != bool(proxy):
            raise AppError('NETWORK_CONFIG', 'Explicit proxy mode requires exactly one proxy.')
        if loopback_origin:
            parts = urlsplit(loopback_origin)
            if parts.scheme != 'http' or parts.hostname != '127.0.0.1' or not parts.port or parts.path or parts.query:
                raise AppError('TEST_ENDPOINT', 'Test injection requires one exact loopback origin.')
        self.loopback_origin = loopback_origin
        self.mode = mode
        self.client = httpx.AsyncClient(trust_env=mode == 'environment', proxy=proxy,
            verify=True, follow_redirects=False,
            limits=httpx.Limits(max_connections=None, max_keepalive_connections=32),
            timeout=httpx.Timeout(120, connect=30, read=120, write=120, pool=120))

    async def close(self) -> None:
        await self.client.aclose()

    def api(self, origin: str, suffix: str) -> str:
        if origin not in (VIDEO_ORIGIN, IMAGE_ORIGIN):
            raise AppError('API_ORIGIN', 'Unapproved API origin.')
        return (self.loopback_origin or origin) + suffix

    async def validate_media(self, url: str) -> str:
        if self.loopback_origin and url.startswith(self.loopback_origin + '/'):
            return url
        if self.loopback_origin:
            raise AppError('TEST_ENDPOINT', 'Offline transport cannot reach another origin.')
        return await asyncio.to_thread(public_https, url, resolve=True)

    async def stream(self, method: str, url: str, output: Path, *, total: float,
                     limit: int, headers: dict | None = None, json_body=None, data=None, files=None,
                     extensions: dict | None = None) -> dict:
        output = safe_path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + '.partial')
        began = time.perf_counter()
        status = None
        try:
            async with asyncio.timeout(total):
                async with self.client.stream(method, url,
                    headers={'Accept-Encoding': 'identity', **(headers or {})}, json=json_body, data=data, files=files,
                    extensions=extensions,
                    timeout=httpx.Timeout(total, connect=min(30, total), read=total, write=total, pool=total)) as response:
                    status = response.status_code
                    received = time.perf_counter()
                    length = response.headers.get('content-length')
                    if length is not None and (not length.isdigit() or int(length) > limit):
                        raise ProviderError('RESPONSE_LIMIT', 'Response exceeds its size limit.', status=status)
                    count = 0
                    h = hashlib.sha256()
                    with temporary.open('wb') as sink:
                        async for chunk in response.aiter_raw():
                            count += len(chunk)
                            if count > limit:
                                raise ProviderError('RESPONSE_LIMIT', 'Response exceeds its size limit.', status=status)
                            sink.write(chunk)
                            h.update(chunk)
                        sink.flush()
                        os.fsync(sink.fileno())
                    if length is not None and count != int(length):
                        raise ProviderError('RESPONSE_TRUNCATED', 'Response body is incomplete.', status=status)
                    replace_file(temporary, output)
                    metadata = {'path': output.name, 'sha256': h.hexdigest(), 'bytes': count, 'httpStatus': status,
                        'headers': {k: response.headers[k] for k in ('content-type', 'content-length', 'retry-after', 'location', 'content-encoding') if k in response.headers},
                        'headersMs': (received-began)*1000, 'totalMs': (time.perf_counter()-began)*1000}
                    if response.headers.get('content-encoding', 'identity') != 'identity':
                        raise ProviderError('RESPONSE_ENCODING', 'Unexpected encoded response preserved.', status=status)
                    return metadata
        except (httpx.HTTPError, TimeoutError, OSError):
            raise ProviderError('PROVIDER_UNREACHABLE', 'Complete response not received; preserve original operation.', status=status) from None

    async def download(self, url: str, target: Path, *, limit: int, total: float = 120,
                       redirects: int = 3) -> dict:
        current = await self.validate_media(url)
        for index in range(redirects + 1):
            headers, extensions = {}, {}
            target_url = current
            if not self.loopback_origin:
                # Pin the validated public IP for this connection, preserving Host
                # and TLS SNI/certificate verification. No second DNS lookup can
                # redirect media requests into a private network.
                parsed = httpx.URL(public_https(current))
                addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.host, 443, type=socket.SOCK_STREAM)
                if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                    raise AppError('URL_UNSAFE', 'Media DNS resolved to a non-public address.')
                target_url = str(parsed.copy_with(host=addresses[0][4][0]))
                headers = {'Host': parsed.host}
                extensions = {'sni_hostname': parsed.host}
            result = await self.stream('GET', target_url, target, total=total, limit=limit, headers=headers, extensions=extensions)
            if result['httpStatus'] in (301, 302, 303, 307, 308):
                location = result['headers'].get('location')
                if not location or index == redirects:
                    raise ProviderError('DOWNLOAD_REDIRECT', 'Media redirect limit reached.')
                current = await self.validate_media(urljoin(current, location))
                continue
            if result['httpStatus'] != 200:
                raise ProviderError('DOWNLOAD_FAILED', 'Media download rejected.', status=result['httpStatus'])
            return result
        raise ProviderError('DOWNLOAD_FAILED', 'Media download incomplete.')


def save_complete(folder: Path, metadata: dict, operation_id: str, request_hash: str) -> dict:
    record = sealed({**metadata, 'operationId': operation_id, 'requestHash': request_hash})
    write_json(folder / 'complete.json', record)
    return record
