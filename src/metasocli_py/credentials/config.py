import base64
import ctypes
import os
import re
import uuid
from pathlib import Path

from ..domain.errors import AppError
from ..persistence.codec import dumps
from ..persistence.files import atomic_write, lock, read_json, read_stable, safe_path

VARIABLES = {'metaso': 'METASOCLI_PY_METASO_API_KEY', 'images': 'METASOCLI_PY_IMAGE_API_KEY'}


def config_dir() -> Path:
    return safe_path(os.environ.get('METASOCLI_PY_CONFIG_DIR', str(Path.home() / '.metasocli-py')))


def runtime_dir() -> Path:
    return safe_path(os.environ.get('METASOCLI_PY_RUNTIME_DIR', str(Path.home() / '.metasocli-py-runtime')))


def crypt(data: bytes, *, decrypt: bool = False) -> bytes:
    if os.name != 'nt':
        raise AppError('CREDENTIAL_PLATFORM', 'Use independent environment variables on this platform.')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = Blob(len(data), buffer), Blob()
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    fn = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise AppError('CREDENTIAL_ENCRYPTION', 'Windows credential protection failed.')
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree(target.pbData)


def save_credential(provider: str, key: str) -> None:
    if provider not in VARIABLES or not re.fullmatch(r'[!-~]{1,4096}', key):
        raise AppError('CREDENTIAL_INVALID', 'Credential must be a token without whitespace.')
    folder = config_dir()
    cipher = crypt(key.encode('utf-8'))
    if crypt(cipher, decrypt=True) != key.encode('utf-8'):
        raise AppError('CREDENTIAL_VERIFY', 'Encrypted credential verification failed; old value preserved.')
    value = {'owner': 'metasocli-py', 'provider': provider, 'format': 'dpapi-current-user-v1',
             'ciphertext': base64.b64encode(cipher).decode('ascii')}
    with lock(folder / 'credentials.lock'):
        file = folder / f'{provider}.json'
        if file.exists():
            atomic_write(folder / 'backups' / f'{provider}-{uuid.uuid4()}.json', read_stable(file))
        atomic_write(file, dumps(value))


def credential(provider: str) -> str:
    env = os.environ.get(VARIABLES[provider])
    if env:
        if not re.fullmatch(r'[!-~]{1,4096}', env):
            raise AppError('CREDENTIAL_INVALID', 'Credential must be a token without whitespace.')
        return env
    file = config_dir() / f'{provider}.json'
    if not file.exists():
        raise AppError('API_KEY_MISSING', 'Independent provider credential is not configured.')
    data = read_json(file)
    if set(data) != {'owner', 'provider', 'format', 'ciphertext'} or data['owner'] != 'metasocli-py' or data['provider'] != provider or data['format'] != 'dpapi-current-user-v1':
        raise AppError('CREDENTIAL_INVALID', 'Credential envelope identity mismatch.')
    try:
        return crypt(base64.b64decode(data['ciphertext'], validate=True), decrypt=True).decode('utf-8')
    except (ValueError, UnicodeError):
        raise AppError('CREDENTIAL_INVALID', 'Credential envelope cannot be decoded.') from None


def status(provider: str, *, decrypt: bool = False) -> dict:
    env = bool(os.environ.get(VARIABLES[provider]))
    present = (config_dir() / f'{provider}.json').exists()
    result = {'provider': provider, 'configured': env or present, 'source': 'environment' if env else 'dpapi' if present else 'missing',
              'decryptChecked': False, 'remoteAuthentication': 'not-tested', 'generation': 'not-tested'}
    if decrypt and (env or present):
        credential(provider)
        result['decryptChecked'] = True
    return result
