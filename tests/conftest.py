import os
import socket
import threading

import pytest


@pytest.fixture(autouse=True)
def offline_guard(monkeypatch, tmp_path):
    """All tests are offline. Loopback is allowed only when explicitly enabled."""
    for key in ('METASO_API_KEY', 'METASOCLI_IMAGE_API_KEY', 'METASOCLI_PY_METASO_API_KEY', 'METASOCLI_PY_IMAGE_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('METASOCLI_PY_CONFIG_DIR', str(tmp_path / 'config'))
    monkeypatch.setenv('METASOCLI_PY_RUNTIME_DIR', str(tmp_path / 'runtime'))
    original = socket.socket.connect
    original_ex = socket.socket.connect_ex
    original_pair = socket.socketpair
    internal = threading.local()

    def allowed(address):
        return (getattr(internal, 'socketpair', False) or os.environ.get('METASOCLI_PY_TEST_LOOPBACK') == '1') and isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1')

    def socketpair(*args, **kwargs):
        internal.socketpair = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            internal.socketpair = False

    def connect(sock, address):
        if not allowed(address):
            raise AssertionError('External network forbidden in offline acceptance')
        return original(sock, address)

    def connect_ex(sock, address):
        if not allowed(address):
            raise AssertionError('External network forbidden in offline acceptance')
        return original_ex(sock, address)

    monkeypatch.setattr(socket.socket, 'connect', connect)
    monkeypatch.setattr(socket.socket, 'connect_ex', connect_ex)
    monkeypatch.setattr(socket, 'socketpair', socketpair)
