"""Development supervisor for ``oarena serve --reload``.

The dashboard process is deliberately a child process.  As soon as a watched
file changes, the supervisor interrupts that child and waits for it to exit
*before* waiting for the tree to settle. This sharply limits exposure to a
half-written bot or engine installation and ensures no further games start
after the change is observed.

Only the standard library is used.  Polling is intentionally conservative and
portable; this command is for a local development server, where correctness is
more useful than adding a platform-specific filesystem dependency.
"""

from __future__ import annotations

import importlib.metadata
import os
import signal
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from . import config as configmod
from .config import Config

__all__ = [
    "FileStamp",
    "PollingWatcher",
    "ReloadSupervisor",
    "child_command",
    "serve",
    "supervisor_command",
    "watch_paths",
]


@dataclass(frozen=True)
class FileStamp:
    """Cheap identity for one watched filesystem entry."""

    modified_ns: int
    changed_ns: int
    size: int
    mode: int


Snapshot = dict[str, FileStamp]


class Child(Protocol):
    """The small slice of :class:`subprocess.Popen` used by the supervisor."""

    pid: int
    returncode: int | None

    def poll(self) -> int | None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def send_signal(self, sig: int) -> None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


_IGNORED_DIR_NAMES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".oarena",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    "__pycache__",
}
_IGNORED_FILE_SUFFIXES = (".pyc", ".pyo", ".swp", ".swo", "~")


def _absolute(path: Path) -> Path:
    """Return a normalized absolute path without requiring it to exist."""

    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _fcode_dist_info_paths() -> list[Path]:
    """Locate fcode's active ``*.dist-info`` directory without importing its engine."""

    try:
        distribution = importlib.metadata.distribution("fcode")
    except importlib.metadata.PackageNotFoundError:
        return []

    found: set[Path] = set()
    private_path = getattr(distribution, "_path", None)
    if private_path is not None:
        path = _absolute(Path(private_path))
        if path.name.endswith(".dist-info"):
            found.add(path)

    # ``_path`` exists on CPython's implementations, but deriving the same
    # directory from public ``files``/``locate_file`` keeps this working with
    # other Distribution implementations too.
    for entry in distribution.files or ():
        parts = Path(str(entry)).parts
        for index, part in enumerate(parts):
            if part.endswith(".dist-info"):
                relative = Path(*parts[: index + 1])
                try:
                    found.add(_absolute(Path(distribution.locate_file(relative))))
                except (OSError, TypeError, ValueError):
                    pass
                break
    return sorted(found, key=os.fspath)


def watch_paths(cfg: Config) -> tuple[Path, ...]:
    """Return roots whose contents can affect a served page or future game.

    The watcher refreshes these roots when project configuration changes and
    periodically thereafter. Consequently a config edit can redirect the
    bot/map directories, and a replacement fcode dist-info directory is picked
    up without paying metadata-discovery cost on every fast file scan.
    """

    package_root = Path(__file__).resolve().parent
    paths = {
        _absolute(package_root),
        _absolute(cfg.bots_dir),
        _absolute(cfg.maps_dir),
        _absolute(cfg.extra_maps_dir),
        _absolute(cfg.config_path),
    }
    try:
        paths.add(_absolute(configmod.fcode_engine_root()))
    except RuntimeError:
        pass
    paths.update(_fcode_dist_info_paths())
    return tuple(sorted(paths, key=os.fspath))


class PollingWatcher:
    """Build metadata snapshots of all reload-sensitive project files."""

    def __init__(
        self,
        cfg: Config,
        *,
        root_refresh_interval: float = 5.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cfg = cfg
        self._config_path = _absolute(cfg.config_path)
        self._root_refresh_interval = max(0.1, float(root_refresh_interval))
        self._monotonic = monotonic
        self._roots: tuple[Path, ...] = ()
        self._roots_cfg: Config | None = None
        self._next_root_refresh = 0.0

    def _current_config(self) -> Config:
        # Config files are commonly briefly invalid while an editor replaces
        # them.  Keep the last valid directory set until the next poll; the
        # config file itself remains watched and therefore still stops/reloads
        # the child immediately.
        try:
            self._cfg = configmod.from_file(self._config_path)
        except configmod.ConfigError:
            pass
        return self._cfg

    def snapshot(self) -> Snapshot:
        cfg = self._current_config()
        now = self._monotonic()
        if cfg != self._roots_cfg or now >= self._next_root_refresh:
            self._roots = watch_paths(cfg)
            self._roots_cfg = cfg
            self._next_root_refresh = now + self._root_refresh_interval
        state_dir = os.fspath(_absolute(cfg.state_dir))
        snapshot: Snapshot = {}
        for root in self._roots:
            self._scan(root, state_dir, snapshot)
        return snapshot

    @staticmethod
    def _scan(root: Path, state_dir: str, snapshot: Snapshot) -> None:
        root_text = os.fspath(_absolute(root))
        state_prefix = state_dir if state_dir.endswith(os.sep) else state_dir + os.sep

        def excluded(path: str) -> bool:
            return path == state_dir or path.startswith(state_prefix)

        if excluded(root_text):
            return
        try:
            root_stat = os.stat(root_text, follow_symlinks=False)
            if not stat.S_ISDIR(root_stat.st_mode):
                PollingWatcher._record_stat(root_text, root_stat, snapshot)
                return
        except OSError:
            return

        pending = [root_text]
        while pending:
            directory = pending.pop()
            try:
                entries = os.scandir(directory)
            except OSError:
                continue
            with entries:
                for entry in entries:
                    path = entry.path
                    if excluded(path):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name not in _IGNORED_DIR_NAMES:
                                pending.append(path)
                            continue
                        if entry.name.endswith(_IGNORED_FILE_SUFFIXES):
                            continue
                        PollingWatcher._record_stat(
                            path,
                            entry.stat(follow_symlinks=False),
                            snapshot,
                        )
                    except OSError:
                        continue

    @staticmethod
    def _record_stat(path: str, file_stat: os.stat_result, snapshot: Snapshot) -> None:
        snapshot[path] = FileStamp(
            modified_ns=file_stat.st_mtime_ns,
            changed_ns=file_stat.st_ctime_ns,
            size=file_stat.st_size,
            mode=file_stat.st_mode,
        )


def _changed_paths(before: Mapping[str, FileStamp], after: Mapping[str, FileStamp]) -> list[str]:
    return sorted(
        path
        for path in before.keys() | after.keys()
        if before.get(path) != after.get(path)
    )


def child_command(
    *,
    host: str,
    port: int,
    open_browser: bool,
    workers: int | None,
    strict_port: bool,
) -> list[str]:
    """Build a fresh, explicitly non-reloading dashboard command."""

    command = [
        sys.executable,
        "-m",
        "oarena",
        "serve",
        "--no-reload",
        "--host",
        host,
        "--port",
        str(port),
        "--open" if open_browser else "--no-open",
    ]
    if workers is not None:
        command.extend(("--workers", str(workers)))
    if strict_port:
        command.append("--strict-port")
    return command


def supervisor_command(
    *,
    host: str,
    port: int,
    open_browser: bool,
    workers: int | None,
    strict_port: bool,
) -> list[str]:
    """Build the command used to re-exec this reload supervisor."""

    command = child_command(
        host=host,
        port=port,
        open_browser=open_browser,
        workers=workers,
        strict_port=strict_port,
    )
    command[command.index("--no-reload")] = "--reload"
    return command


def _linux_process_groups(root_pid: int) -> set[int]:
    """Return process groups in a Linux process tree, including its root.

    Game workers deliberately create their own sessions. Capturing every group
    before shutdown lets escalation reap those workers even if the dashboard
    process wedges before :meth:`App.close` can cancel them itself. On systems
    without procfs this conservatively falls back to the dashboard's group.
    """

    groups = {int(root_pid)}
    pending = [int(root_pid)]
    seen: set[int] = set()
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        try:
            groups.add(os.getpgid(pid))
        except OSError:
            pass
        # A subprocess belongs to the Linux task (thread) that spawned it.
        # ThreadPoolExecutor workers therefore appear under their worker TID's
        # children file, not necessarily under task/<process-pid>/children.
        try:
            task_dirs = list(Path(f"/proc/{pid}/task").iterdir())
        except OSError:
            continue
        for task_dir in task_dirs:
            try:
                children = (task_dir / "children").read_text(encoding="ascii")
            except OSError:
                continue
            for raw in children.split():
                try:
                    child_pid = int(raw)
                except ValueError:
                    continue
                if child_pid not in seen:
                    pending.append(child_pid)
    groups.discard(os.getpgrp())
    return groups


def _signal_process_group(group: int, sig: int) -> None:
    """Send a signal to a POSIX process group without breaking import on Windows."""

    killpg = getattr(os, "killpg", None)
    if killpg is None:  # pragma: no cover - only called on POSIX
        raise NotImplementedError("process-group signals are unavailable")
    killpg(group, sig)


class ReloadSupervisor:
    """Run and safely replace dashboard child processes as watched files change."""

    def __init__(
        self,
        cfg: Config,
        *,
        host: str,
        port: int,
        open_browser: bool,
        workers: int | None,
        strict_port: bool,
        poll_interval: float = 0.25,
        debounce: float = 0.75,
        restart_backoff: float = 0.5,
        max_restart_backoff: float = 10.0,
        watcher: PollingWatcher | None = None,
        stop_event: threading.Event | None = None,
        popen: Callable[..., Child] = subprocess.Popen,
        monotonic: Callable[[], float] = time.monotonic,
        wait: Callable[[float], bool] | None = None,
        signal_process_group: Callable[[int, int], None] = _signal_process_group,
        process_groups: Callable[[int], set[int]] = _linux_process_groups,
        execvpe: Callable[[str, Sequence[str], Mapping[str, str]], object] = os.execvpe,
    ) -> None:
        self.cfg = cfg
        self.host = host
        self.port = int(port)
        self.open_browser = bool(open_browser)
        self.workers = workers
        self.strict_port = bool(strict_port)
        self.poll_interval = max(0.01, float(poll_interval))
        self.debounce = max(0.0, float(debounce))
        self.restart_backoff = max(0.0, float(restart_backoff))
        self.max_restart_backoff = max(self.restart_backoff, float(max_restart_backoff))
        self.watcher = watcher or PollingWatcher(cfg)
        self.stop_event = stop_event or threading.Event()
        self._popen = popen
        self._monotonic = monotonic
        self._wait = wait or self.stop_event.wait
        self._signal_process_group = signal_process_group
        self._process_groups = process_groups
        self._execvpe = execvpe
        self._child: Child | None = None
        self._package_root = os.fspath(_absolute(Path(__file__).resolve().parent))

    def _spawn(self, *, open_browser: bool) -> Child:
        command = child_command(
            host=self.host,
            port=self.port,
            open_browser=open_browser,
            workers=self.workers,
            strict_port=self.strict_port,
        )
        child = self._popen(
            command,
            cwd=self.cfg.root,
            env=os.environ.copy(),
            start_new_session=True,
        )
        self._child = child
        return child

    def _signal_groups(self, groups: set[int], sig: int) -> None:
        for group in sorted(groups):
            try:
                self._signal_process_group(group, sig)
            except ProcessLookupError:
                pass

    def _stop_child(self, child: Child) -> None:
        """Interrupt the child, escalating only if graceful shutdown gets stuck."""

        if child.poll() is not None:
            self._child = None
            return
        try:
            if os.name == "nt":  # pragma: no cover - deployment target is Linux
                child.terminate()
            else:
                groups = self._process_groups(child.pid)
                self._signal_groups({child.pid}, signal.SIGINT)
            child.wait(timeout=12.0)
        except subprocess.TimeoutExpired:
            if os.name == "nt":  # pragma: no cover
                child.terminate()
            else:
                groups.update(self._process_groups(child.pid))
                self._signal_groups(groups, signal.SIGTERM)
            try:
                child.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                if os.name == "nt":  # pragma: no cover
                    child.kill()
                else:
                    groups.update(self._process_groups(child.pid))
                    self._signal_groups(groups, signal.SIGKILL)
                child.wait()
        except ProcessLookupError:
            pass
        finally:
            self._child = None

    def _requires_reexec(self, paths: Sequence[str]) -> bool:
        prefix = self._package_root + os.sep
        return any(path == self._package_root or path.startswith(prefix) for path in paths)

    def _reexec(self) -> None:
        """Replace the supervisor so edits to its own implementation take effect."""

        command = supervisor_command(
            host=self.host,
            port=self.port,
            open_browser=False,
            workers=self.workers,
            strict_port=self.strict_port,
        )
        print("reload: oarena changed; replacing reload supervisor", flush=True)
        try:
            self._execvpe(command[0], command, os.environ.copy())
        except OSError as exc:
            # A failed exec should not take down an otherwise usable dashboard.
            print(f"reload: supervisor replacement failed: {exc}", flush=True)

    def _settle(self, snapshot: Snapshot) -> Snapshot | None:
        """Wait with the child down until the watched trees stay unchanged."""

        stable_since = self._monotonic()
        while not self.stop_event.is_set():
            elapsed = self._monotonic() - stable_since
            if elapsed >= self.debounce:
                return snapshot
            if self._wait(min(self.poll_interval, self.debounce - elapsed)):
                return None
            current = self.watcher.snapshot()
            changed = _changed_paths(snapshot, current)
            if changed:
                self._announce_change(changed, continuing=True)
                snapshot = current
                stable_since = self._monotonic()
        return None

    def _backoff(self, snapshot: Snapshot, delay: float) -> Snapshot | None:
        """Wait after a crash while continuing to fold edits into the baseline."""

        deadline = self._monotonic() + delay
        while not self.stop_event.is_set():
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                return snapshot
            if self._wait(min(self.poll_interval, remaining)):
                return None
            current = self.watcher.snapshot()
            changed = _changed_paths(snapshot, current)
            if changed:
                self._announce_change(changed, continuing=True)
                settled = self._settle(current)
                return settled
        return None

    @staticmethod
    def _announce_change(paths: Sequence[str], *, continuing: bool = False) -> None:
        sample = ", ".join(paths[:3])
        if len(paths) > 3:
            sample += f", … (+{len(paths) - 3})"
        verb = "more changes" if continuing else "change detected"
        print(f"reload: {verb}: {sample}", flush=True)

    def request_stop(self, _signum: int | None = None, _frame: object | None = None) -> None:
        self.stop_event.set()

    def run(self) -> None:
        baseline = self.watcher.snapshot()
        open_browser = self.open_browser
        backoff = self.restart_backoff
        previous_handlers: dict[int, object] = {}
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, self.request_stop)

        print(
            "reload: watching oarena, bots, maps, config and fcode; "
            "games are aborted before each restart",
            flush=True,
        )
        try:
            while not self.stop_event.is_set():
                child = self._spawn(open_browser=open_browser)
                open_browser = False
                started = self._monotonic()
                changed = False

                while not self.stop_event.is_set():
                    code = child.poll()
                    if code is not None:
                        break
                    if self._wait(self.poll_interval):
                        break
                    current = self.watcher.snapshot()
                    paths = _changed_paths(baseline, current)
                    if not paths:
                        continue

                    # Stop first, debounce second: after a change is observed,
                    # no active game continues while the tree settles.
                    self._announce_change(paths)
                    previous = baseline
                    self._stop_child(child)
                    changed = True
                    baseline = current
                    settled = self._settle(baseline)
                    if settled is None:
                        break
                    baseline = settled
                    if self._requires_reexec(_changed_paths(previous, baseline)):
                        self._reexec()
                    backoff = self.restart_backoff
                    print("reload: files stable; restarting server", flush=True)
                    break

                if self.stop_event.is_set():
                    if self._child is child:
                        self._stop_child(child)
                    break
                if changed:
                    continue

                code = child.poll()
                if code is None:
                    # Defensive: normally only the stop event or a source
                    # change can leave the inner loop while the child lives.
                    self._stop_child(child)
                    continue
                self._child = None
                runtime = self._monotonic() - started
                if runtime >= 30.0:
                    backoff = self.restart_backoff
                delay = backoff
                backoff = min(self.max_restart_backoff, max(0.1, backoff * 2.0))
                print(
                    f"reload: server exited with status {code}; restarting in {delay:.1f}s",
                    flush=True,
                )
                settled = self._backoff(baseline, delay)
                if settled is None:
                    break
                baseline = settled
        finally:
            child = self._child
            if child is not None:
                self._stop_child(child)
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)


def serve(
    cfg: Config,
    *,
    host: str = "127.0.0.1",
    port: int = 7878,
    open_browser: bool = True,
    workers: int | None = None,
    strict_port: bool = False,
) -> None:
    """Run the reload supervisor until SIGINT or SIGTERM."""

    ReloadSupervisor(
        cfg,
        host=host,
        port=port,
        open_browser=open_browser,
        workers=workers,
        strict_port=strict_port,
    ).run()
