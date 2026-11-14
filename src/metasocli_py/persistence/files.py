import os
import stat
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import portalocker

from ..domain.errors import AppError
from .codec import MAX_RECORD, dumps, loads, sha256


def native_path(path: Path) -> str:
    """Only called after lexical validation; never accept a user device path."""
    value = str(path)
    return '\\\\?\\' + value if os.name == 'nt' else value


def safe_path(value: Path | str) -> Path:
    raw = str(value)
    if raw.startswith(('\\\\', '//')) or '\x00' in raw:
        raise AppError('PATH_UNSAFE', 'UNC/device paths are forbidden.')
    path = Path(os.path.abspath(raw))
    if str(path).startswith(('\\\\', '//')):
        raise AppError('PATH_UNSAFE', 'Normalized device/UNC paths are forbidden.')
    for part in path.parts[1:]:
        if ':' in part or part.endswith(('.', ' ')) or part.split('.')[0].lower() in {
            'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(10)), *(f'lpt{i}' for i in range(10))}:
            raise AppError('PATH_UNSAFE', 'Reserved path or alternate data stream.')
    for current in [*reversed(path.parents), path]:
        try:
            info = os.lstat(native_path(current))
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise AppError('PATH_UNSAFE', 'Symlinks and reparse points are forbidden.')
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise AppError('PATH_UNSAFE', 'Hardlinked files are forbidden.')
    return path


def project_path(root: Path | str, relative: str) -> Path:
    base = safe_path(root)
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts or rel.drive:
        raise AppError('PATH_ESCAPE', 'Expected a project-relative path.')
    target = safe_path(base / rel)
    if not target.is_relative_to(base):
        raise AppError('PATH_ESCAPE', 'Path escapes the project.')
    return target


def identity(info: os.stat_result) -> tuple:
    if not info.st_ino:
        raise AppError('FILE_IDENTITY_UNAVAILABLE', 'Stable file identity is unavailable.')
    # CPython/Windows path stat may expose creation time where fstat exposes
    # NTFS change time. Compare ctime only between reads of the same handle.
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def read_stable(path: Path | str, limit: int = MAX_RECORD) -> bytes:
    path = safe_path(path)
    before_path = path.stat()
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit or identity(before) != identity(before_path):
            raise AppError('FILE_LIMIT', 'Expected a stable bounded regular file.')
        # Read one byte past the observed size, not one byte past the category
        # limit: allocating 128 MiB for a tiny transaction journal is needless.
        # The handle/path identity and final size checks still reject growth.
        data = stream.read(before.st_size + 1)
        after = os.fstat(stream.fileno())
        final = safe_path(path).stat()
        if len(data) > limit or len(data) != after.st_size or identity(before) != identity(after) or before.st_ctime_ns != after.st_ctime_ns or identity(after) != identity(final):
            raise AppError('FILE_CHANGED', 'File changed during read.')
    return data


def sync_directory(path: Path) -> None:
    if os.name != 'nt':
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def replace_file(source: Path, target: Path) -> None:
    for attempt in range(16):
        safe_path(source)
        safe_path(target)
        try:
            os.replace(native_path(source), native_path(target))
            sync_directory(target.parent)
            return
        except PermissionError:
            if attempt == 15:
                raise AppError('REPLACE_BUSY', 'Atomic replacement remained busy; old file preserved.') from None
            time.sleep(min(0.1, 0.01 * (attempt + 1)))


def atomic_write(path: Path | str, data: bytes) -> None:
    target = safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    safe_path(target)
    temp = target.with_name(target.name + '.tmp-' + str(uuid.uuid4()))
    try:
        with open(native_path(temp), 'xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        replace_file(temp, target)
    finally:
        if os.path.exists(native_path(temp)):
            os.unlink(native_path(temp))  # Only our uncommitted unique temporary.


def write_json(path: Path | str, value: object) -> None:
    data = dumps(value)
    if len(data) > MAX_RECORD:
        raise AppError('FILE_LIMIT', 'Record exceeds 8 MiB.')
    atomic_write(path, data)


def read_json(path: Path | str) -> dict:
    value = loads(read_stable(path))
    if not isinstance(value, dict):
        raise AppError('INVALID_RECORD', 'Expected an object record.')
    return value


@contextmanager
def lock(path: Path | str, timeout: float = 10) -> Iterator[None]:
    target = safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = target.open('a+b')
    began = time.monotonic()
    acquired = False
    try:
        while True:
            try:
                portalocker.lock(handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
                acquired = True
                break
            except portalocker.LockException:
                if time.monotonic() - began >= timeout:
                    raise AppError('LOCK_BUSY', 'Another live process owns the operation lock.') from None
                time.sleep(0.01)
        if os.fstat(handle.fileno()).st_ino != safe_path(target).stat().st_ino:
            raise AppError('LOCK_IDENTITY', 'Lock path identity changed.')
        yield
    finally:
        if acquired:
            portalocker.unlock(handle)
        handle.close()
        # Stable lock inode is deliberately retained, including after owner death.


def is_locked(path: Path) -> bool:
    try:
        with lock(path, timeout=0):
            return False
    except AppError as error:
        if error.code == 'LOCK_BUSY':
            return True
        raise


def transaction(root: Path, writes: dict[str, bytes], commit: str) -> None:
    """Caller holds short story lock. Journal + immutable staging; manifest is last."""
    txn = project_path(root, '.metasocli-py/transactions/' + str(uuid.uuid4()))
    txn.mkdir(parents=True)
    entries = []
    for index, (name, data) in enumerate(writes.items()):
        target = project_path(root, name)
        stage = txn / f'{index}.bin'
        atomic_write(stage, data)
        entries.append({'path': name, 'stage': stage.name, 'sha256': sha256(data),
                        'previous': sha256(read_stable(target, max(len(data), MAX_RECORD))) if target.exists() else None})
    record = {'commit': commit, 'entries': entries, 'state': 'prepared'}
    write_json(txn / 'journal.json', record)
    write_json(project_path(root, '.metasocli-py/transaction-pending.json'), {'path': str(txn.relative_to(root)).replace('\\', '/')})
    apply_transaction(root, txn, record)
    write_json(project_path(root, '.metasocli-py/transaction-pending.json'), {'path': None})


def apply_transaction(root: Path, txn: Path, record: dict) -> None:
    entries = sorted(record['entries'], key=lambda item: item['path'] == record['commit'])
    for item in entries:
        stage = read_stable(project_path(txn, item['stage']), 128 * 1024 * 1024)
        if sha256(stage) != item['sha256']:
            raise AppError('TRANSACTION_CORRUPT', 'Transaction staging bytes changed.')
        target = project_path(root, item['path'])
        current = sha256(read_stable(target, 128 * 1024 * 1024)) if target.exists() else None
        if current == item['sha256']:
            continue
        if current != item['previous']:
            raise AppError('TRANSACTION_CONFLICT', 'Newer content conflicts with pending transaction.')
        atomic_write(target, stage)
    write_json(txn / 'journal.json', {**record, 'state': 'committed'})


def recover_transactions(root: Path) -> None:
    pointer = project_path(root, '.metasocli-py/transaction-pending.json')
    if not pointer.exists():
        return
    pending = read_json(pointer)['path']
    if pending:
        txn = project_path(root, pending)
        record = read_json(txn / 'journal.json')
        if record['state'] == 'prepared':
            apply_transaction(root, txn, record)
        write_json(pointer, {'path': None})
