"""Isolated installed-wheel smoke, launched with -I and a PATH without Node."""
# ruff: noqa: E402 -- the isolation audit must precede every application import.
import json
import os
import shutil
import socket
import struct
import sys
import threading
import uuid
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

source_root = Path(__file__).resolve().parents[1]/'src'


def audit(event, args):
    if event in ('open', 'os.listdir', 'os.scandir') and args and isinstance(args[0], (str, bytes, Path)):
        path = str(args[0]).replace('\\', '/').lower()
        if path.startswith(('e:/metasocli/', 'e:/libcli/', str(source_root).replace('\\', '/').lower()+'/')):
            raise RuntimeError('Wheel isolation rejected old/source directory access')


sys.addaudithook(audit)
real_connect = socket.socket.connect


def connect(sock, address):
    if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1'):
        raise RuntimeError('Wheel smoke denied external network')
    return real_connect(sock, address)


socket.socket.connect = connect
assert shutil.which('node') is None and shutil.which('npm') is None
import metasocli_py
from metasocli_py.application.assets import register_asset
from metasocli_py.application.skills import payloads
from metasocli_py.application.story import import_story, initialize
from metasocli_py.cli import Services, main
from metasocli_py.domain.text import utf16_length
from metasocli_py.providers.http import Http
from metasocli_py.providers.metaso import Metaso
from metasocli_py.video.execution import ExecutionOptions

assert 'site-packages' in metasocli_py.__file__
assert len([path for path in payloads() if path.endswith('/SKILL.md')]) == 6


def box(kind, data):
    return struct.pack('>I4s', len(data)+8, kind)+data


def mp4():
    mvhd, tkhd, hdlr = bytearray(100), bytearray(84), bytearray(24)
    struct.pack_into('>II', mvhd, 12, 1000, 4000)
    struct.pack_into('>II', tkhd, 76, 432*65536, 768*65536)
    hdlr[8:12] = b'vide'
    return box(b'ftyp', b'isom\0\0\0\0isom')+box(b'moov', box(b'mvhd', mvhd)+box(b'trak', box(b'tkhd', tkhd)+box(b'mdia', box(b'hdlr', hdlr))))+box(b'mdat', b'\0'*100)


posts = []
task_prefix = uuid.uuid4().hex


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, data, mime='application/json'):
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        assert self.path == '/api/minimax/v2/video_generation'
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        posts.append(request)
        self.reply(json.dumps({'task_id': task_prefix + '-' + str(len(posts))}).encode())

    def do_GET(self):
        if self.path.startswith('/api/minimax/v2/query/video_generation/'):
            identifier = self.path.rsplit('/', 1)[1]
            self.reply(json.dumps({'task': {'id': identifier, 'model': 'MiniMax-H3', 'task_type': 'generation',
                'status': 'completed', 'content': {'url': origin+'/video.mp4'}}}).encode())
        else:
            assert 'Authorization' not in self.headers
            self.reply(mp4(), 'video/mp4')


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
origin = f'http://127.0.0.1:{server.server_port}'
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
base = Path(sys.argv[1])
base.mkdir(parents=True, exist_ok=True)
os.environ['METASOCLI_PY_RUNTIME_DIR'] = str(base/'runtime')
os.environ['METASOCLI_PY_CONFIG_DIR'] = str(base/'config')
try:
    for entry in (sys.argv[2],):
        root = base/entry
        initialize(root, entry)
        prompt = '旁白：甲😀。\n人物：乙。\n'
        source = base/(entry+'.txt')
        source.write_bytes(('\ufeff'+prompt.replace('\n', '\r\n')).encode('utf-8'))
        segment = {'id': 's1', 'start': 0, 'end': utf16_length(prompt), 'duration': 4}
        recipes = []
        if entry.endswith('旁白'):
            recipes = [{'assetId': 'narrator', 'kind': 'narration', 'prompt': 'synthetic test voice'}]
            segment['narration'] = {'assetId': 'narrator', 'cues': [{'start': 0, 'end': utf16_length('旁白：甲😀。')}]}
        import_story(root, {'episodeId': 'ep', 'kind': 'video-prompts', 'source': str(source), 'offsetEncoding': 'utf16', 'segments': [segment], 'recipes': recipes})
        if recipes:
            audio = base/'synthetic.wav'
            with wave.open(str(audio), 'wb') as sink:
                sink.setnchannels(1)
                sink.setsampwidth(2)
                sink.setframerate(16000)
                sink.writeframes(b'\0'*64000)
            register_asset(root, 'narrator', audio)
        services = Services(video_factory=lambda: Metaso(Http(loopback_origin=origin), 'synthetic'),
                            execution_options=ExecutionOptions(max_polls=1, poll_seconds=0, capacity_poll=.01))
        command = ['video', 'run', '--root', str(root), '--episodes', 'ep', '--confirm']
        assert main(command, services) == 0
        assert main(command, services) == 0
    assert len(posts) == 1
    assert len(posts[0]['content']) == (2 if entry.endswith('旁白') else 1)
    assert all(p['context_ir_enabled'] is True for p in posts)
    print(json.dumps({'installedFrom': metasocli_py.__file__, 'entry': entry, 'posts': len(posts),
                      'nodeAvailable': False, 'oldSourceAccessible': False, 'replayPosts': 0}))
finally:
    server.shutdown()
    server.server_close()
    thread.join()
