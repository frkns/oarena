"""Focused tests for the stdlib development-server reload supervisor."""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from conftest import Project, write_bot
from oarena import reloader, server as servermod
from oarena.cli import main


def _stamp(value: int) -> reloader.FileStamp:
    return reloader.FileStamp(value, value, value, value)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class SequenceWatcher:
    def __init__(self, snapshots: list[reloader.Snapshot], trace: list[str]) -> None:
        self.snapshots = snapshots
        self.trace = trace
        self.index = 0

    def snapshot(self) -> reloader.Snapshot:
        self.trace.append(f"snapshot{self.index}")
        value = self.snapshots[min(self.index, len(self.snapshots) - 1)]
        self.index += 1
        return value


class FakeChild:
    def __init__(
        self,
        number: int,
        trace: list[str],
        *,
        exit_code: int | None = None,
        stop_on_poll: Any = None,
    ) -> None:
        self.pid = 1000 + number
        self.number = number
        self.trace = trace
        self.returncode = exit_code
        self.stop_on_poll = stop_on_poll

    def poll(self) -> int | None:
        self.trace.append(f"poll{self.number}")
        if self.stop_on_poll is not None:
            self.stop_on_poll.set()
            self.stop_on_poll = None
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        self.trace.append(f"reap{self.number}:{timeout}")
        self.returncode = -int(signal.SIGINT)
        return self.returncode

    def send_signal(self, sig: int) -> None:
        self.trace.append(f"signal{self.number}:{int(sig)}")

    def terminate(self) -> None:
        self.trace.append(f"terminate{self.number}")

    def kill(self) -> None:
        self.trace.append(f"kill{self.number}")


def test_child_command_is_an_explicit_clean_non_reloading_serve() -> None:
    command = reloader.child_command(
        host="0.0.0.0",
        port=9000,
        open_browser=False,
        workers=3,
        strict_port=True,
    )

    assert command[1:4] == ["-m", "oarena", "serve"]
    assert "--no-reload" in command
    assert "--no-open" in command
    assert command[command.index("--workers") + 1] == "3"
    assert "--strict-port" in command


def test_supervisor_command_reexecs_with_reload_enabled() -> None:
    command = reloader.supervisor_command(
        host="127.0.0.1",
        port=7878,
        open_browser=False,
        workers=2,
        strict_port=True,
    )

    assert "--reload" in command
    assert "--no-reload" not in command
    assert "--no-open" in command


def test_change_interrupts_and_reaps_child_before_debounce_and_restart(project: Project) -> None:
    trace: list[str] = []
    clock = FakeClock()
    stop_event = reloader.threading.Event()
    before = {"bot.py": _stamp(1)}
    after = {"bot.py": _stamp(2)}
    watcher = SequenceWatcher([before, after, after, after], trace)
    children: list[FakeChild] = []

    def wait(delay: float) -> bool:
        trace.append(f"wait:{delay:.2f}")
        clock.now += delay
        return stop_event.is_set()

    def popen(command: list[str], **_kwargs: Any) -> FakeChild:
        number = len(children) + 1
        trace.append(f"spawn{number}:{'--open' in command}")
        child = FakeChild(
            number,
            trace,
            stop_on_poll=stop_event if number == 2 else None,
        )
        children.append(child)
        return child

    supervisor = reloader.ReloadSupervisor(
        project.cfg,
        host="127.0.0.1",
        port=7878,
        open_browser=True,
        workers=None,
        strict_port=False,
        poll_interval=0.1,
        debounce=0.2,
        watcher=watcher,  # type: ignore[arg-type]
        stop_event=stop_event,
        popen=popen,
        monotonic=clock,
        wait=wait,
        signal_process_group=lambda group, sig: trace.append(
            f"group{group - 1000}:{int(sig)}"
        ),
        process_groups=lambda pid: {pid},
    )
    supervisor.run()

    signal_index = trace.index(f"group1:{int(signal.SIGINT)}")
    reap_index = next(i for i, item in enumerate(trace) if item.startswith("reap1:"))
    restart_index = next(i for i, item in enumerate(trace) if item.startswith("spawn2:"))
    assert signal_index < reap_index < restart_index
    assert any(item.startswith("wait:") for item in trace[reap_index + 1 : restart_index])
    assert "spawn1:True" in trace
    assert "spawn2:False" in trace  # reloads do not keep opening browser tabs


def test_crashed_child_restarts_after_backoff(project: Project) -> None:
    trace: list[str] = []
    clock = FakeClock()
    stop_event = reloader.threading.Event()
    unchanged = {"bot.py": _stamp(1)}
    watcher = SequenceWatcher([unchanged] * 8, trace)
    children: list[FakeChild] = []

    def wait(delay: float) -> bool:
        trace.append(f"wait:{delay:.2f}")
        clock.now += delay
        return stop_event.is_set()

    def popen(_command: list[str], **_kwargs: Any) -> FakeChild:
        number = len(children) + 1
        trace.append(f"spawn{number}")
        child = FakeChild(
            number,
            trace,
            exit_code=9 if number == 1 else None,
            stop_on_poll=stop_event if number == 2 else None,
        )
        children.append(child)
        return child

    supervisor = reloader.ReloadSupervisor(
        project.cfg,
        host="127.0.0.1",
        port=7878,
        open_browser=False,
        workers=None,
        strict_port=False,
        poll_interval=0.1,
        restart_backoff=0.3,
        watcher=watcher,  # type: ignore[arg-type]
        stop_event=stop_event,
        popen=popen,
        monotonic=clock,
        wait=wait,
        signal_process_group=lambda group, sig: trace.append(
            f"group{group - 1000}:{int(sig)}"
        ),
        process_groups=lambda pid: {pid},
    )
    supervisor.run()

    assert trace.index("spawn1") < trace.index("wait:0.10") < trace.index("spawn2")
    assert clock.now >= 0.3


def test_polling_watcher_ignores_oarena_state_and_python_cache(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reloader, "watch_paths", lambda _cfg: (project.root,))
    watched = project.cfg.bots_dir / "alpha" / "main.py"
    watched.parent.mkdir(parents=True, exist_ok=True)
    watched.write_text("ONE", encoding="utf-8")
    cache = project.root / "__pycache__" / "main.pyc"
    cache.parent.mkdir()
    cache.write_bytes(b"ONE")
    db = project.cfg.state_dir / "watch-noise.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(b"ONE")
    watcher = reloader.PollingWatcher(project.cfg)
    initial = watcher.snapshot()

    db.write_bytes(b"TWO")
    cache.write_bytes(b"TWO")
    ignored_only = watcher.snapshot()
    assert initial == ignored_only

    watched.write_text("TWO-TWO", encoding="utf-8")
    assert watcher.snapshot() != initial
    assert str(db) not in initial


def test_polling_watcher_detects_changes_in_a_mounted_bot_catalog(
    project: Project, tmp_path: Path
) -> None:
    upstream = tmp_path / "pantheon-bots"
    bot = write_bot(upstream, "Heimdall_v6")
    (project.cfg.bots_dir / "pantheon").symlink_to(
        upstream,
        target_is_directory=True,
    )
    watcher = reloader.PollingWatcher(project.cfg)
    initial = watcher.snapshot()

    (bot / "main.py").write_text("CHANGED", encoding="utf-8")

    assert str(bot / "main.py") in initial
    assert watcher.snapshot() != initial


def test_watch_paths_cover_project_oarena_and_fcode(
    project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = tmp_path / "fcode"
    dist_info = tmp_path / "fcode-9.9.dist-info"
    monkeypatch.setattr(reloader.configmod, "fcode_engine_root", lambda: engine)
    monkeypatch.setattr(reloader, "_fcode_dist_info_paths", lambda: [dist_info])

    paths = set(reloader.watch_paths(project.cfg))

    assert project.cfg.bots_dir in paths
    assert project.cfg.maps_dir in paths
    assert project.cfg.extra_maps_dir in paths
    assert project.cfg.config_path in paths
    assert engine in paths
    assert dist_info in paths
    assert Path(reloader.__file__).resolve().parent in paths


def test_watch_paths_include_only_direct_external_bot_mounts(
    project: Project, tmp_path: Path
) -> None:
    direct = tmp_path / "direct-bots"
    nested = tmp_path / "nested-bots"
    direct.mkdir()
    nested.mkdir()
    (project.cfg.bots_dir / "pantheon").symlink_to(
        direct,
        target_is_directory=True,
    )
    group = project.cfg.bots_dir / "group"
    group.mkdir()
    (group / "nested-link").symlink_to(nested, target_is_directory=True)

    paths = set(reloader.watch_paths(project.cfg))

    assert direct.resolve() in paths
    assert nested.resolve() not in paths


def test_serve_cli_preserves_defaults_and_forwards_reload_options(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(project.root)
    direct: list[dict[str, Any]] = []
    reloads: list[dict[str, Any]] = []
    monkeypatch.setattr(servermod, "serve", lambda _cfg, **kwargs: direct.append(kwargs))
    monkeypatch.setattr(reloader, "serve", lambda _cfg, **kwargs: reloads.append(kwargs))
    runner = CliRunner()

    result = runner.invoke(main, ["serve", "--no-open"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert direct == [
        {
            "host": "127.0.0.1",
            "port": 7878,
            "open_browser": False,
            "workers": None,
            "strict_port": False,
        }
    ]
    assert reloads == []

    result = runner.invoke(
        main,
        [
            "serve",
            "--reload",
            "--strict-port",
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
            "--workers",
            "2",
            "--no-open",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert reloads == [
        {
            "host": "0.0.0.0",
            "port": 9000,
            "open_browser": False,
            "workers": 2,
            "strict_port": True,
        }
    ]


def test_stop_escalates_only_after_grace_timeout(project: Project) -> None:
    trace: list[str] = []

    class StuckChild(FakeChild):
        def wait(self, timeout: float | None = None) -> int:
            trace.append(f"wait:{timeout}")
            if timeout is not None:
                raise subprocess.TimeoutExpired("child", timeout)
            self.returncode = -9
            return self.returncode

    child = StuckChild(1, trace)
    supervisor = reloader.ReloadSupervisor(
        project.cfg,
        host="127.0.0.1",
        port=7878,
        open_browser=False,
        workers=None,
        strict_port=False,
        signal_process_group=lambda group, sig: trace.append(
            f"group{group - 1000}:{int(sig)}"
        ),
        process_groups=lambda pid: {pid, pid + 1},
    )

    supervisor._stop_child(child)

    assert trace == [
        "poll1",
        f"group1:{int(signal.SIGINT)}",
        "wait:12.0",
        f"group1:{int(signal.SIGTERM)}",
        f"group2:{int(signal.SIGTERM)}",
        "wait:3.0",
        f"group1:{int(signal.SIGKILL)}",
        f"group2:{int(signal.SIGKILL)}",
        "wait:None",
    ]


@pytest.mark.skipif(
    os.name == "nt" or not Path("/proc/self/task").is_dir(),
    reason="Linux procfs process-tree discovery",
)
def test_process_group_discovery_finds_child_spawned_by_thread() -> None:
    ready: queue.Queue[subprocess.Popen[bytes]] = queue.Queue()
    release = threading.Event()

    def spawn_from_pool_thread() -> None:
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            start_new_session=True,
        )
        ready.put(process)
        release.wait(timeout=10.0)
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()

    thread = threading.Thread(target=spawn_from_pool_thread)
    thread.start()
    process = ready.get(timeout=5.0)
    try:
        assert process.pid in reloader._linux_process_groups(os.getpid())
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        release.set()
        thread.join(timeout=5.0)
    assert not thread.is_alive()


def test_oarena_source_change_reexecs_supervisor_after_reaping(project: Project) -> None:
    trace: list[str] = []
    clock = FakeClock()
    stop_event = reloader.threading.Event()
    source = str(Path(reloader.__file__).resolve())
    before = {source: _stamp(1)}
    after = {source: _stamp(2)}
    watcher = SequenceWatcher([before, after, after, after], trace)
    children: list[FakeChild] = []

    def wait(delay: float) -> bool:
        clock.now += delay
        return stop_event.is_set()

    def popen(_command: list[str], **_kwargs: Any) -> FakeChild:
        number = len(children) + 1
        trace.append(f"spawn{number}")
        child = FakeChild(
            number,
            trace,
            stop_on_poll=stop_event if number == 2 else None,
        )
        children.append(child)
        return child

    def execvpe(_file: str, command: Any, _env: Any) -> None:
        trace.append(f"exec:{'--reload' in command}")

    supervisor = reloader.ReloadSupervisor(
        project.cfg,
        host="127.0.0.1",
        port=7878,
        open_browser=False,
        workers=None,
        strict_port=False,
        poll_interval=0.1,
        debounce=0.2,
        watcher=watcher,  # type: ignore[arg-type]
        stop_event=stop_event,
        popen=popen,
        monotonic=clock,
        wait=wait,
        signal_process_group=lambda group, sig: trace.append(
            f"group{group - 1000}:{int(sig)}"
        ),
        process_groups=lambda pid: {pid},
        execvpe=execvpe,
    )
    supervisor.run()

    assert trace.index("reap1:12.0") < trace.index("exec:True") < trace.index("spawn2")
