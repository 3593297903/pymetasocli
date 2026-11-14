"""Synthetic provider with real loopback HTTP, never production credentials."""
import base64
import io
import json
import struct
import threading
import time
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image


def png(size=(1920, 1088), color=(20, 40, 80)):
    stream = io.BytesIO()
    Image.new('RGB', size, color).save(stream, format='PNG')
    return stream.getvalue()


def box(kind, data):
    return struct.pack('>I4s', len(data)+8, kind) + data


def mp4(duration=4, width=432, height=768):
    mvhd = bytearray(100)
    struct.pack_into('>II', mvhd, 12, 1000, int(duration*1000))
    tkhd = bytearray(84)
    struct.pack_into('>II', tkhd, 76, width*65536, height*65536)
    hdlr = bytearray(24)
    hdlr[8:12] = b'vide'
    moov = box(b'mvhd', mvhd) + box(b'trak', box(b'tkhd', tkhd) + box(b'mdia', box(b'hdlr', hdlr)))
    return box(b'ftyp', b'isom\0\0\0\0isom') + box(b'moov', moov) + box(b'mdat', b'\0'*100)


class FakeProvider:
    def __init__(self):
        self.events = []
        self.requests = []
        self.gets = []
        self.tasks = {}
        self.lock = threading.Lock()
        self.create_delay = .12
        self.image_delay = .02
        self.image_delays = {}
        self.image_batch_gate = 0
        self.image_gate = threading.Event()
        self.image_pictures = {}
        self.download_delay = .15
        self.fail_images = set()
        self.fail_video = False
        self.truncate = False
        self.status_code = 200
        self.query_error = False
        self.query_status = 'completed'
        self.query_delays = {}
        self.query_ids = {}
        self.active_queries = self.max_queries = 0
        self.video_reject_status = None
        self.image_url = False
        self.fail_download = False
        self.picture = png()
        self.active_creates = self.max_creates = 0
        self.live = self.max_live = 0
        fake = self
        class Server(ThreadingHTTPServer):
            daemon_threads = True
            request_queue_size = 1024
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def reply(self, body, mime='application/json', status=200, truncate=False):
                try:
                    self.send_response(status)
                    self.send_header('Content-Type', mime)
                    self.send_header('Content-Length', str(len(body)+10 if truncate else len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                if self.headers.get('Content-Type', '').startswith('multipart/'):
                    mime = BytesParser(policy=policy.default).parsebytes(
                        b'Content-Type: ' + self.headers['Content-Type'].encode() + b'\r\nMIME-Version: 1.0\r\n\r\n' + raw)
                    fields, files = {}, []
                    for part in mime.iter_parts():
                        name = part.get_param('name', header='content-disposition')
                        filename = part.get_filename()
                        if filename:
                            files.append({'field': name, 'filename': filename, 'mime': part.get_content_type(), 'bytes': part.get_payload(decode=True)})
                        else:
                            fields[name] = part.get_payload(decode=True).decode()
                else:
                    fields, files = json.loads(raw), []
                with fake.lock:
                    fake.requests.append({'path': self.path, 'fields': fields, 'files': files, 'time': time.perf_counter()})
                if self.path.startswith('/v1/images/'):
                    if fake.image_batch_gate:
                        with fake.lock:
                            if len(fake.requests) >= fake.image_batch_gate:
                                fake.image_gate.set()
                        if not fake.image_gate.wait(90):
                            self.reply(b'{"error":"synthetic dispatch gate timed out"}', status=503)
                            return
                    time.sleep(fake.image_delays.get(fields['prompt'], fake.image_delay))
                    if fake.status_code != 200 or fields['prompt'] in fake.fail_images:
                        self.reply(b'{"error":{"code":"synthetic_error"}}', status=fake.status_code if fake.status_code != 200 else 500)
                        return
                    picture = fake.image_pictures.get(fields['prompt'], fake.picture)
                    output = {'url': fake.origin + '/image.png'} if fake.image_url else {'b64_json': base64.b64encode(picture).decode()}
                    self.reply(json.dumps({'data': [output]}).encode(), truncate=fake.truncate)
                    fake.events.append(('image-response', fields['prompt'], time.perf_counter()))
                    return
                if fake.video_reject_status:
                    self.reply(b'{"error":"synthetic authorization rejection"}', status=fake.video_reject_status)
                    return
                with fake.lock:
                    fake.active_creates += 1
                    fake.max_creates = max(fake.max_creates, fake.active_creates)
                    identifier = str(len(fake.tasks)+1)
                    fake.tasks[identifier] = {'request': fields, 'ir': self.path.endswith('h3_context_ir'), 'done': False}
                    fake.live += 1
                    fake.max_live = max(fake.max_live, fake.live)
                    fake.events.append(('create', identifier, time.perf_counter()))
                time.sleep(fake.create_delay)
                with fake.lock:
                    fake.active_creates -= 1
                if fake.fail_video:
                    self.reply(b'{"error":{"code":"ambiguous"}}', status=502)
                else:
                    self.reply(json.dumps({'task_id': identifier}).encode())
            def do_GET(self):
                fake.gets.append({'path': self.path, 'headers': dict(self.headers), 'time': time.perf_counter()})
                if self.path.startswith('/api/minimax/v2/query/video_generation/'):
                    identifier = self.path.rsplit('/', 1)[1]
                    with fake.lock:
                        fake.active_queries += 1
                        fake.max_queries = max(fake.max_queries, fake.active_queries)
                    time.sleep(fake.query_delays.get(identifier, 0))
                    with fake.lock:
                        fake.active_queries -= 1
                    if fake.query_error:
                        self.reply(b'{"error":"temporary"}', status=503)
                        return
                    identifier = self.path.rsplit('/', 1)[1]
                    with fake.lock:
                        task = fake.tasks[identifier]
                        if not task['done'] and fake.query_status in ('completed', 'failed', 'cancelled'):
                            task['done'] = True
                            fake.live -= 1
                            fake.events.append(('terminal', identifier, time.perf_counter()))
                    content = {'prompt': task['request']['content'][0]['text']} if task['ir'] else {'url': fake.origin + '/video/' + identifier}
                    self.reply(json.dumps({'task': {'id': fake.query_ids.get(identifier, identifier), 'model': 'MiniMax-H3',
                        'task_type': 'h3_context_ir' if task['ir'] else 'generation', 'status': fake.query_status, 'content': content}}).encode())
                elif self.path.startswith('/video/'):
                    identifier = self.path.rsplit('/', 1)[1]
                    time.sleep(fake.download_delay)
                    if fake.fail_download:
                        self.reply(b'bad', status=503)
                    else:
                        self.reply(mp4(fake.tasks[identifier]['request']['duration']), 'video/mp4')
                    fake.events.append(('download', identifier, time.perf_counter()))
                elif self.path == '/image.png':
                    time.sleep(fake.download_delay)
                    self.reply(fake.picture if not fake.fail_download else b'broken', 'image/png', status=503 if fake.fail_download else 200)
                elif self.path == '/slow':
                    time.sleep(.3)
                    self.reply(b'{}')
                else:
                    self.reply(b'{}', status=404)
        self.server = Server(('127.0.0.1', 0), Handler)
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
