"""Local browser interface; serves assets and coordinates one render at a time."""
import io
import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .config import (RenderConfig, PALETTES, WEB_MAX_CONNECTIONS,
                     WEB_SOCKET_TIMEOUT, WEB_UPLOAD_TIMEOUT)
from .logic.pipeline import render_audio
from .logic.styles import STYLES
from .media import TemporarySession, media_workspace, ffmpeg_version

ASSETS = Path(__file__).with_name('web_static')
MAX_UPLOAD = 512 * 1024 * 1024


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, root):
        self.temporary = TemporarySession(root)
        try:
            super().__init__(address, StudioHandler)
        except Exception:
            self.temporary.close()
            raise
        self.root = Path(root)
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.job = {'state': 'idle'}
        self.stopping = threading.Event()
        self.worker = None
        self.preview = None
        self.preview_discarded = False
        self.connections = threading.BoundedSemaphore(WEB_MAX_CONNECTIONS)

    def process_request(self, request, client_address):
        if not self.connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.connections.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connections.release()

    def render(self, source, output, config):
        def progress(done, total):
            if self.stopping.is_set():
                raise RuntimeError('Render stopped with the server.')
            with self.lock:
                self.job['progress'] = round(100 * done / total)
        try:
            with media_workspace(self.temporary.path):
                render_audio(source, output, config, progress=progress)
            with self.lock:
                if config.duration is not None and self.preview_discarded:
                    self.job = {'state': 'idle'}
                    return
                if config.duration is not None:
                    self.preview = output.read_bytes()
                    output.unlink()
                self.job.update(state='done', progress=100, filename=output.name,
                                preview=config.duration is not None)
        except Exception as error:
            with self.lock:
                self.job.update(state='error', error=str(error))
        finally:
            source.unlink(missing_ok=True)
            if config.duration is not None:
                output.unlink(missing_ok=True)

    def server_close(self):
        self.stopping.set()
        if self.worker:
            self.worker.join(timeout=10)
        self.preview = None
        super().server_close()
        if self.worker is None or not self.worker.is_alive():
            self.temporary.close()


class StudioHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(WEB_SOCKET_TIMEOUT)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "media-src 'self' blob:; connect-src 'self'; img-src 'self' data:; "
                         "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass

    def reply(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def trusted_host(self):
        host = f'127.0.0.1:{self.server.server_port}'
        return (self.headers.get_all('Host') == [host]
                and self.headers.get('Origin', f'http://{host}') == f'http://{host}'
                and self.headers.get('Sec-Fetch-Site') not in ('cross-site', 'same-site'))

    def do_GET(self):
        if not self.trusted_host():
            return self.reply(403, {'error': 'Open the app using its local address.'})
        path = urlsplit(self.path).path
        if path == '/api/options':
            with self.server.lock:
                job = dict(self.server.job)
            return self.reply(200, {'styles': list(STYLES), 'palettes': PALETTES,
                                    'token': self.server.token, 'job': job})
        if path == '/api/status':
            with self.server.lock:
                return self.reply(200, self.server.job)
        assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                  '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if path in assets:
            name, mime = assets[path]
            return self.send_file(ASSETS / name, mime)
        if path == '/video':
            with self.server.lock:
                job = dict(self.server.job)
                preview = self.server.preview
            if job.get('state') == 'done' and job.get('preview'):
                if preview is not None:
                    return self.send_file(None, 'video/mp4', preview)
            elif job.get('state') == 'done':
                return self.send_file(self.server.root / 'outputs' / job['filename'], 'video/mp4')
        self.reply(404, {'error': 'Not found.'})

    def send_file(self, path, mime, data=None):
        size = len(data) if data is not None else path.stat().st_size
        start, end, status = 0, size - 1, 200
        value = self.headers.get('Range')
        if value:
            try:
                unit, interval = value.split('=')
                first, last = interval.split('-')
                if unit != 'bytes' or ',' in interval:
                    raise ValueError()
                start = int(first) if first else max(0, size - int(last))
                end = min(int(last), size-1) if first and last else size-1
                if start < 0 or start > end or start >= size:
                    raise ValueError()
                status = 206
            except ValueError:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.end_headers()
                return
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(end-start+1))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Cache-Control', 'no-store')
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        if path is not None and urlsplit(self.path).query == 'download':
            self.send_header('Content-Disposition', f'attachment; filename="{path.name}"')
        self.end_headers()
        try:
            with (io.BytesIO(data) if data is not None else path.open('rb')) as stream:
                stream.seek(start)
                remaining = end-start+1
                while remaining:
                    chunk = stream.read(min(1024*1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        if not self.trusted_host() or self.headers.get('X-Studio-Token') != self.server.token:
            return self.reply(403, {'error': 'Refresh the app and try again.'})
        url = urlsplit(self.path)
        if url.path == '/api/discard-preview':
            with self.server.lock:
                if self.server.job.get('preview'):
                    self.server.preview_discarded = True
                    self.server.preview = None
                    if self.server.job['state'] == 'done':
                        self.server.job = {'state': 'idle'}
            return self.reply(200, {'state': 'idle'})
        if url.path != '/api/render':
            return self.reply(404, {'error': 'Not found.'})
        try:
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
                raise ValueError('A single Content-Length is required.')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_UPLOAD:
                raise ValueError('Choose an audio file smaller than 512 MB.')
            args = parse_qs(url.query)
            style = args.get('style', ['line'])[0]
            if style not in STYLES:
                raise ValueError('Choose a valid style.')
            preview = args.get('preview', ['false'])[0] == 'true'
            config = RenderConfig(duration=10 if preview else None, style=style, palette=args.get('palette', ['aurora'])[0],
                                  brain_mode=args.get('brain_mode', ['connected'])[0])
        except ValueError as error:
            return self.reply(400, {'error': str(error)})
        with self.server.lock:
            if self.server.job['state'] in ('uploading', 'rendering'):
                return self.reply(409, {'error': 'A video is already being created.'})
            self.server.preview = None
            self.server.preview_discarded = False
            self.server.job = {'state': 'uploading', 'progress': 0, 'preview': preview}
        identifier = secrets.token_hex(8)
        directory = self.server.temporary.path
        source = directory / f'{identifier}.audio'
        destination = directory if preview else self.server.root / 'outputs'
        output = destination / f"{style.replace(' ', '-')}-{config.palette}-{identifier}.mp4"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            deadline = time.monotonic() + WEB_UPLOAD_TIMEOUT
            with source.open('xb') as stream:
                remaining = length
                while remaining:
                    if time.monotonic() >= deadline:
                        raise ValueError('Upload took too long. Please try again.')
                    self.connection.settimeout(min(WEB_SOCKET_TIMEOUT, deadline - time.monotonic()))
                    chunk = self.rfile.read1(min(1024*1024, remaining))
                    if not chunk:
                        raise ValueError('Upload was interrupted. Please try again.')
                    stream.write(chunk)
                    remaining -= len(chunk)
            with self.server.lock:
                if self.server.stopping.is_set():
                    raise ValueError('The studio is stopping.')
                self.server.job = {'state': 'rendering', 'progress': 0, 'preview': preview}
            self.server.worker = threading.Thread(target=self.server.render, args=(source, output, config), daemon=True)
            self.server.worker.start()
            self.reply(202, {'state': 'rendering'})
        except (OSError, ValueError) as error:
            source.unlink(missing_ok=True)
            with self.server.lock:
                self.server.job = {'state': 'error', 'error': str(error)}
            self.reply(400, self.server.job)


def main():
    root = Path(__file__).resolve().parents[2]
    print(ffmpeg_version(), flush=True)
    server = StudioServer(('127.0.0.1', 0), root)
    address = f'http://127.0.0.1:{server.server_port}'
    print(f'\n  AUDIO / FORM\n\n  Open {address}\n\n  Keep this window open while using the app.\n  Close it or press Ctrl+C to stop the server.\n  Finished videos are saved in outputs.\n', flush=True)
    webbrowser.open(address)
    try:
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        print('\nStopping the studio...')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
