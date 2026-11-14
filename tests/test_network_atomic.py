import ctypes
import os
import threading
import time
import uuid
from pathlib import Path

import pytest

from metasocli_py.domain.errors import AppError
from metasocli_py.persistence.files import atomic_write, lock, read_stable
from metasocli_py.providers.http import Http
from metasocli_py.video.capacity import Capacity
from tests.fake_http import FakeProvider


@pytest.mark.asyncio
async def test_direct_proxy_environment_real_http(tmp_path, monkeypatch):
    monkeypatch.setenv('METASOCLI_PY_TEST_LOOPBACK', '1')
    with FakeProvider() as destination, FakeProvider() as proxy:
        monkeypatch.setenv('HTTP_PROXY', proxy.origin)
        monkeypatch.setenv('http_proxy', proxy.origin)
        monkeypatch.setenv('NO_PROXY', '')
        monkeypatch.setenv('no_proxy', '')
        for mode in ('direct', 'environment', 'proxy'):
            http = Http(mode=mode, proxy=proxy.origin if mode == 'proxy' else None)
            await http.stream('GET', destination.origin+'/probe', tmp_path/f'{mode}.json', total=2, limit=1024)
            await http.close()
        assert len(destination.gets) == 1
        assert len(proxy.gets) == 2
        assert all(r['path'] == destination.origin+'/probe' for r in proxy.gets)
        assert os.environ['HTTP_PROXY'] == proxy.origin


def test_windows_actual_sharing_denial_bounded_atomic_retry(tmp_path):
    file = tmp_path/'atomic.txt'
    file.write_bytes(b'old')
    if os.name != 'nt':
        atomic_write(file, b'new')
        assert file.read_bytes() == b'new'
        return
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(file), 0x80000000, 1, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value
    thread = threading.Thread(target=lambda: (time.sleep(.1), kernel.CloseHandle(handle)), daemon=True)
    thread.start()
    started = time.monotonic()
    atomic_write(file, b'new')
    thread.join()
    assert .08 < time.monotonic()-started < 2
    assert file.read_bytes() == b'new'
    handle = kernel.CreateFileW(str(file), 0x80000000, 1, None, 3, 0x80, None)
    try:
        with pytest.raises(AppError, match='old file preserved'):
            atomic_write(file, b'never-replaces')
        assert file.read_bytes() == b'new'
    finally:
        kernel.CloseHandle(handle)


def test_file_identity_changes_between_stat_and_open_rejected(tmp_path, monkeypatch):
    file, replacement = tmp_path/'victim', tmp_path/'replacement'
    file.write_bytes(b'original')
    replacement.write_bytes(b'replaced')
    original = Path.open
    swapped = False
    def open_path(path, *args, **kwargs):
        nonlocal swapped
        if path == file and not swapped:
            os.replace(replacement, file)
            swapped = True
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', open_path)
    with pytest.raises(AppError):
        read_stable(file)


def test_five_restored_held_tasks_stop_new_reservations(tmp_path):
    runtime, root = tmp_path/'runtime', tmp_path/'story'
    root.mkdir()
    capacity = Capacity(runtime)
    project = str(uuid.uuid4())
    owner = root/'owner.lock'
    plan = {'projectId': project, 'batchId': str(uuid.uuid4()), 'scopeHash': 'a'*64, 'concurrency': 4}
    operations = []
    with lock(owner):
        ticket = capacity.ticket(root, plan, 8, owner)
        for index in range(5):
            operation = str(uuid.uuid4())
            job = {'operationId': operation, 'projectId': project, 'requestHash': 'a'*64, 'inputHash': 'b'*64}
            if index == 4:
                capacity.apply({'operationId': operations[0], 'projectId': project, 'requestHash': 'a'*64,
                                'taskId': '0', 'sequence': capacity.issue(operations[0]), 'reason': 'query_unavailable'})
            assert capacity.reserve(ticket, job, root, owner)
            operations.append(operation)
            capacity.apply({'operationId': operation, 'projectId': project, 'requestHash': 'a'*64,
                            'taskId': str(index), 'sequence': capacity.issue(operation), 'reason': 'create_accepted'})
        capacity.apply({'operationId': operations[0], 'projectId': project, 'requestHash': 'a'*64,
                        'taskId': '0', 'sequence': capacity.issue(operations[0]), 'reason': 'remote_active_recovered'})
        ledger = capacity.read()
        assert sum(s['capacity']['state'] == 'held' for s in ledger['slots'].values()) == 5
        assert ledger['slots'][operations[0]]['capacity']['lastRelease']
        assert ledger['slots'][operations[0]]['capacity']['lastRestore']
        job = {'operationId': str(uuid.uuid4()), 'projectId': project, 'requestHash': 'a'*64, 'inputHash': 'b'*64}
        assert not capacity.reserve(ticket, job, root, owner)
