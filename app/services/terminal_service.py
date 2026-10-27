"""Shell interaktif berbasis PTY (bash) dengan cwd = folder project."""
import asyncio
import codecs
import fcntl
import os
import pty
import signal
import struct
import subprocess
import termios
from pathlib import Path

_SENSITIVE = ("SECRET", "TOKEN", "PASSWORD", "PASSWD", "API_KEY", "PRIVATE_KEY")
_SENSITIVE_PREFIX = ("JWT_", "DATABASE_", "GITHUB_", "GH_", "CODESPACES")

_active: dict[int, int] = {}


def acquire(user_id: int, limit: int) -> bool:
    if _active.get(user_id, 0) >= limit:
        return False
    _active[user_id] = _active.get(user_id, 0) + 1
    return True


def release(user_id: int) -> None:
    n = _active.get(user_id, 0) - 1
    if n <= 0:
        _active.pop(user_id, None)
    else:
        _active[user_id] = n


def build_env() -> dict[str, str]:
    """Environment shell: salin env server tapi buang secret/token (mis. GITHUB_TOKEN)."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not any(s in k.upper() for s in _SENSITIVE) and not k.upper().startswith(_SENSITIVE_PREFIX)
    }
    env.update(
        TERM="xterm-256color",
        LANG=env.get("LANG", "C.UTF-8"),
        PS1=r"\[\e[1;36m\]zephyr\[\e[0m\]:\[\e[1;34m\]\W\[\e[0m\]\$ ",
    )
    env.setdefault("HOME", str(Path.home()))
    return env


class TerminalSession:
    def __init__(self, cwd: Path, shell: str = "/bin/bash"):
        self.cwd = cwd
        self.shell = shell
        self.proc: subprocess.Popen | None = None
        self.master_fd: int | None = None
        self.queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._closed = False

    def start(self, cols: int = 80, rows: int = 24) -> None:
        self._loop = asyncio.get_running_loop()
        master, slave = pty.openpty()

        def _preexec() -> None:
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        try:
            self.proc = subprocess.Popen(
                [self.shell, "--noprofile", "--norc", "-i"],
                stdin=slave, stdout=slave, stderr=slave,
                cwd=str(self.cwd), env=build_env(),
                preexec_fn=_preexec, close_fds=True,
            )
        except Exception:
            os.close(master)
            raise
        finally:
            os.close(slave)

        self.master_fd = master
        os.set_blocking(master, False)
        self.resize(cols, rows)
        self._loop.add_reader(master, self._on_readable)

    def _on_readable(self) -> None:
        try:
            data = os.read(self.master_fd, 4096)  # type: ignore[arg-type]
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            self._detach_reader()
            self.queue.put_nowait(None)
            return
        self.queue.put_nowait(data)

    def _detach_reader(self) -> None:
        if self.master_fd is not None and self._loop is not None:
            try:
                self._loop.remove_reader(self.master_fd)
            except Exception:
                pass

    def decode(self, data: bytes) -> str:
        return self._decoder.decode(data)

    def write(self, text: str) -> None:
        if self.master_fd is None or self._closed:
            return
        data = text.encode("utf-8")
        try:
            while data:
                try:
                    n = os.write(self.master_fd, data)
                    data = data[n:]
                except BlockingIOError:
                    break  # buffer penuh: buang sisa (input manusia kecil)
        except OSError:
            pass

    def resize(self, cols: int, rows: int) -> None:
        if self.master_fd is None:
            return
        cols = max(10, min(int(cols), 500))
        rows = max(2, min(int(rows), 200))
        try:
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        except OSError:
            pass

    async def close(self) -> None:
        """Matikan shell beserta seluruh child process-nya (npm, node, dst.)."""
        if self._closed:
            return
        self._closed = True
        self._detach_reader()
        proc = self.proc
        if proc is not None and proc.poll() is None:
            try:
                pgid = os.getpgid(proc.pid)
            except ProcessLookupError:
                pgid = None
            for sig in (signal.SIGHUP, signal.SIGTERM):
                try:
                    os.killpg(pgid, sig) if pgid else proc.send_signal(sig)
                except ProcessLookupError:
                    break
                try:
                    await asyncio.to_thread(proc.wait, 1.5)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if proc.poll() is None:
                try:
                    os.killpg(pgid, signal.SIGKILL) if pgid else proc.kill()
                except ProcessLookupError:
                    pass
                await asyncio.to_thread(proc.wait)
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None
