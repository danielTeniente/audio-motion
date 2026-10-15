"""FFmpeg decoding and encoding; owns temporary files and subprocess cleanup."""
from contextlib import contextmanager
from contextvars import ContextVar
import os
from pathlib import Path
import re
import shutil
import sys
import subprocess
import tempfile
import uuid
import numpy as np
import imageio_ffmpeg
from .config import MEDIA_INPUT_FORMATS, MEDIA_DECODE_TIMEOUT, application_root

SAMPLE_RATE = 22050
_workspace = ContextVar('media_workspace', default=None)


def ffmpeg_path():
    explicit = os.environ.get('IMAGEIO_FFMPEG_EXE')
    if explicit:
        return explicit
    if getattr(sys, 'frozen', False):
        local = application_root() / 'ffmpeg' / 'bin'
    else:
        local = Path(__file__).resolve().parents[2] / '.tools' / 'ffmpeg' / 'bin'
    executable = local / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
    if executable.is_file():
        return str(executable)
    return imageio_ffmpeg.get_ffmpeg_exe()


def ffmpeg_version():
    return subprocess.check_output([ffmpeg_path(), '-version'], text=True, timeout=10).splitlines()[0]


@contextmanager
def media_workspace(path):
    """Keep a render's intermediate audio and video inside its owned session."""
    token = _workspace.set(Path(path))
    try:
        yield
    finally:
        _workspace.reset(token)


def _lock_file(stream, acquire):
    stream.seek(0)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK if acquire else msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), (fcntl.LOCK_EX | fcntl.LOCK_NB) if acquire else fcntl.LOCK_UN)


def _is_link(path):
    """Also reject Windows junctions/reparse points before any cleanup."""
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)


def _remove_session(path, parent):
    # Only marked, app-created UUID directories under this exact parent qualify.
    if not re.fullmatch(r'[0-9a-f]{32}', path.name) or _is_link(path):
        return False
    if path.resolve().parent != parent.resolve():
        return False
    marker = path / '.studio-session'
    if _is_link(marker) or marker.read_text() != 'audio-form-session-v1':
        return False
    for directory, folders, files in os.walk(path, followlinks=False):
        for name in folders + files:
            child = Path(directory) / name
            if _is_link(child) or not child.resolve().is_relative_to(path.resolve()):
                return False
    # Preserve the marker if a locked data file prevents cleanup, so the next
    # launch can retry rather than leaving unrecognized temporary audio behind.
    for child in path.iterdir():
        if child.name in ('.lock', '.studio-session'):
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    (path / '.lock').unlink()
    marker.unlink()
    path.rmdir()
    return True


class TemporarySession:
    """An OS lock distinguishes abandoned work from other running app sessions."""
    def __init__(self, root):
        root = Path(root).resolve()
        self.parent = root / '.tmp' / 'studio-sessions'
        if not self.parent.resolve().is_relative_to(root):
            raise ValueError('Temporary session storage must stay inside the project.')
        self.parent.mkdir(parents=True, exist_ok=True)
        if not self.parent.resolve().is_relative_to(root) or _is_link(self.parent):
            raise ValueError('Temporary session storage must stay inside the project.')
        self.cleanup_abandoned()
        self.path = self.parent / uuid.uuid4().hex
        self.path.mkdir(mode=0o700)
        self.lock = (self.path / '.lock').open('x+b')
        self.lock.write(b'0')
        self.lock.flush()
        _lock_file(self.lock, True)
        (self.path / '.studio-session').write_text('audio-form-session-v1')

    def cleanup_abandoned(self):
        for path in self.parent.iterdir():
            try:
                if not path.is_dir() or _is_link(path) or not re.fullmatch(r'[0-9a-f]{32}', path.name):
                    continue
                lock = path / '.lock'
                if _is_link(lock):
                    continue
                with lock.open('r+b') as stream:
                    _lock_file(stream, True)
                    _lock_file(stream, False)
                _remove_session(path, self.parent)
            except (OSError, ValueError):
                # Active/locked files are never forced; retry on a later launch.
                continue

    def close(self):
        if self.lock.closed:
            return
        _lock_file(self.lock, False)
        self.lock.close()
        try:
            _remove_session(self.path, self.parent)
        except OSError:
            pass  # Another process may still hold a file after interruption.


def local_input_options():
    """Restrict media parsing to direct local files, never network playlists."""
    return ["-protocol_whitelist", "file", "-format_whitelist", MEDIA_INPUT_FORMATS]


@contextmanager
def decoded_audio(path: Path, duration: float | None = None):
    with tempfile.TemporaryDirectory(prefix="voice-audio-", dir=_workspace.get()) as directory:
        decoded = Path(directory) / "analysis.f32"
        command = [ffmpeg_path(), "-nostdin", "-v", "error", *local_input_options(), "-i", str(Path(path).resolve()),
                   "-map", "0:a:0", "-vn"]
        if duration is not None:
            command += ["-t", str(duration)]
        command += ["-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", str(decoded)]
        try:
            result = subprocess.run(command, capture_output=True, timeout=MEDIA_DECODE_TIMEOUT)
        except subprocess.TimeoutExpired as error:
            raise ValueError("Audio decoding took too long. Try a shorter or simpler audio file.") from error
        if result.returncode:
            raise ValueError("Cannot decode audio: " + result.stderr.decode(errors="replace").strip())
        if not decoded.exists() or decoded.stat().st_size < 4:
            raise ValueError("The input contains no audio samples.")
        samples = np.memmap(decoded, mode="r", dtype="<f4")
        try:
            yield samples
        finally:
            samples._mmap.close()


def encode_video(frames, source: Path, output: Path, config, duration: float, overwrite=False):
    """Stream RGB frames; publish the completed file only after FFmpeg succeeds."""
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".voice-", suffix=".mp4", dir=_workspace.get() or output.parent)
    os.close(descriptor)
    temporary = Path(name)
    command = [ffmpeg_path(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{config.width}x{config.height}", "-r", str(config.fps), "-i", "pipe:0",
               *local_input_options(), "-i", str(Path(source).resolve()), "-map", "0:v:0", "-map", "1:a:0",
               "-c:v", "libx264", "-preset", config.encoder_preset, "-crf", "20", "-pix_fmt", "yuv420p",
               "-map_metadata", "-1", "-map_chapters", "-1",
               "-c:a", "aac", "-b:a", "192k", "-t", str(duration),
               "-movflags", "+faststart", str(temporary)]
    try:
        with tempfile.TemporaryFile(dir=_workspace.get()) as errors:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
            try:
                try:
                    for frame in frames:
                        process.stdin.write(frame.tobytes())
                    process.stdin.close()
                except BrokenPipeError:
                    pass
                code = process.wait()
                if code:
                    errors.seek(0)
                    raise RuntimeError("Video export failed: " + errors.read().decode(errors="replace").strip())
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
                try:
                    process.stdin.close()
                except BrokenPipeError:
                    pass
        if overwrite:
            os.replace(temporary, output)
        elif os.name == "nt":
            # Windows rename is atomic and refuses an existing destination.
            os.rename(temporary, output)
        else:
            # Atomic no-clobber publication, even if another render finishes first.
            os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
