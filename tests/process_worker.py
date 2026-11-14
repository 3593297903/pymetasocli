"""Test-only child entry: explicit injected loopback, no production endpoint override."""
import argparse
import os
import socket
import sys
import time
from pathlib import Path

if __name__ == '__main__':
    for key in ('METASO_API_KEY', 'METASOCLI_IMAGE_API_KEY', 'METASOCLI_PY_METASO_API_KEY', 'METASOCLI_PY_IMAGE_API_KEY'):
        os.environ.pop(key, None)
    parser = argparse.ArgumentParser()
    parser.add_argument('--origin')
    parser.add_argument('--checkpoint')
    parser.add_argument('--marker', type=Path)
    parser.add_argument('--hold-lock', type=Path)
    parser.add_argument('--transaction', type=Path)
    opts, argv = parser.parse_known_args()
    original_connect = socket.socket.connect
    def connect(sock, address):
        if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1'):
            raise RuntimeError('Offline child rejected non-loopback network')
        return original_connect(sock, address)
    socket.socket.connect = connect
    original_connect_ex = socket.socket.connect_ex
    def connect_ex(sock, address):
        if not isinstance(address, tuple) or address[0] not in ('127.0.0.1', '::1'):
            raise RuntimeError('Offline child rejected non-loopback network')
        return original_connect_ex(sock, address)
    socket.socket.connect_ex = connect_ex
    def checkpoint(point, _job=None):
        if point == opts.checkpoint:
            opts.marker.write_text(point, encoding='utf-8')
            time.sleep(60)
            raise RuntimeError('Parent did not terminate the test child')
    from metasocli_py.persistence.files import lock
    if opts.hold_lock:
        with lock(opts.hold_lock):
            opts.marker.write_text('held', encoding='utf-8')
            time.sleep(60)
    elif opts.transaction:
        import metasocli_py.persistence.files as fs
        root = opts.transaction
        real = fs.atomic_write
        def write(path, data):
            real(path, data)
            if Path(path) == root / 'a.txt':
                checkpoint('transaction-mid')
        fs.atomic_write = write
        with lock(root / '.metasocli-py/story.lock'):
            fs.transaction(root, {'a.txt': b'new-a', 'b.txt': b'new-b'}, 'b.txt')
    else:
        from metasocli_py.cli import Services, main
        from metasocli_py.providers.http import Http
        from metasocli_py.providers.metaso import Metaso
        from metasocli_py.providers.yiciyuang import Yiciyuang
        from metasocli_py.video.execution import ExecutionOptions
        services = Services(
            video_factory=lambda: Metaso(Http(loopback_origin=opts.origin), 'synthetic-video-token'),
            image_factory=lambda: Yiciyuang(Http(loopback_origin=opts.origin), 'synthetic-image-token'),
            image_checkpoint=checkpoint,
            execution_options=ExecutionOptions(max_polls=2, poll_seconds=.01, capacity_wait=.1, capacity_poll=.01, checkpoint=checkpoint))
        sys.exit(main(argv, services))
