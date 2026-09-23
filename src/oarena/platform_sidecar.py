"""Serve the bounded FCode platform boundary over a filesystem Unix socket.

Run this process outside oarena's game-worker network/home sandbox, then set
``OARENA_PLATFORM_SOCKET`` for ``oarena serve``.  The RPC surface is deliberately
limited to the explicit dashboard operations, including one unrated-match write.
"""

from __future__ import annotations

import argparse
import errno
import grp
import logging
import os
import signal
import socket
import socketserver
import stat
import threading
import time
from pathlib import Path
from typing import Any

from oarena.fcode_platform import FcodePlatform, PlatformError
from oarena.platform_rpc import (
    _MAX_JSON_BODY_BYTES,
    _MAX_REPLAY_BODY_BYTES,
    _MAX_REQUEST_BODY_BYTES,
    _ProtocolError,
    _exact_keys,
    _json_bytes,
    _recv_frame,
    _recv_eof,
    _safe_error_message,
    _send_frame,
    _socket_path,
    _validate_call,
)

__all__ = ["PlatformSidecarServer", "main"]


_LOG = logging.getLogger("oarena.platform_sidecar")
_DEFAULT_WORKERS = 8
_MAX_WORKERS = 32
_DEFAULT_CONNECTION_TIMEOUT_S = 20.0


def _safe_platform_error(exc: PlatformError) -> dict[str, Any]:
    code = exc.code
    if isinstance(code, bool) or not isinstance(code, int) or not 400 <= code <= 599:
        return {"code": 502, "message": "FCode platform request failed"}
    try:
        message = _safe_error_message(exc.message)
    except _ProtocolError:
        return {"code": 502, "message": "FCode platform request failed"}
    result: dict[str, Any] = {"code": code, "message": message}
    retry_after_s = exc.retry_after_s
    if (
        not isinstance(retry_after_s, bool)
        and isinstance(retry_after_s, int)
        and 0 <= retry_after_s <= 7 * 24 * 60 * 60
    ):
        result["retry_after_s"] = retry_after_s
    if exc.outcome_unknown is True:
        result["outcome_unknown"] = True
    return result


def _dispatch(platform: Any, op: str, args: dict[str, Any]) -> dict[str, Any] | bytes:
    """Explicit dispatch keeps the socket from becoming a generic method bridge."""
    if op == "session":
        return platform.session()
    if op == "scrim_profile":
        return platform.scrim_profile()
    if op == "team_search":
        return platform.team_search(**args)
    if op == "platform_maps":
        return platform.platform_maps()
    if op == "request_unrated":
        return platform.request_unrated(**args)
    if op == "ladder":
        return platform.ladder(limit=args["limit"])
    if op == "test_runs":
        return platform.test_runs(limit=args["limit"])
    if op == "matches":
        return platform.matches(**args)
    if op == "match":
        return platform.match(args["match_id"])
    if op == "replay":
        return platform.replay(args["match_id"], args["game"])
    # ``_validate_call`` makes this unreachable. Keep the guard adjacent to the
    # dispatcher so adding a validator alone cannot expose a new method.
    raise PlatformError(400, "unsupported platform operation")


class _PlatformRpcHandler(socketserver.BaseRequestHandler):
    server: "PlatformSidecarServer"
    request: socket.socket

    def handle(self) -> None:
        peer = self.request
        peer.settimeout(self.server.connection_timeout_s)
        op: str | None = None
        try:
            request_deadline = time.monotonic() + self.server.connection_timeout_s
            header, body = _recv_frame(
                peer,
                max_body_bytes=_MAX_REQUEST_BODY_BYTES,
                deadline=request_deadline,
            )
            # Every valid client half-closes after its sole request. This makes
            # trailing frames/bytes an error instead of an ambiguous second call.
            _recv_eof(
                peer,
                deadline=request_deadline,
            )
            if body:
                raise _ProtocolError("RPC requests cannot have bodies")
            request = _exact_keys(
                header,
                allowed=frozenset({"op", "args"}),
                required=frozenset({"op", "args"}),
                name="request field",
            )
            op, args = _validate_call(request["op"], request["args"])
            if op == "replay":
                if not self.server.replay_slots.acquire(
                    timeout=self.server.connection_timeout_s
                ):
                    raise PlatformError(503, "FCode platform replay queue is busy")
                try:
                    result = _dispatch(self.server.platform, op, args)
                    if not isinstance(result, bytes):
                        raise PlatformError(502, "FCode platform request failed")
                    if len(result) > _MAX_REPLAY_BODY_BYTES:
                        raise PlatformError(502, "FCode platform replay is too large")
                    _send_frame(peer, {"ok": True, "kind": "replay"}, result)
                finally:
                    self.server.replay_slots.release()
                return
            result = _dispatch(self.server.platform, op, args)
            if not isinstance(result, dict):
                raise PlatformError(
                    502,
                    "FCode platform request failed",
                    outcome_unknown=op == "request_unrated",
                )
            try:
                encoded = _json_bytes(result)
            except _ProtocolError as exc:
                raise PlatformError(
                    502,
                    "FCode platform request failed",
                    outcome_unknown=op == "request_unrated",
                ) from exc
            if len(encoded) > _MAX_JSON_BODY_BYTES:
                raise PlatformError(
                    502,
                    "FCode platform response is too large",
                    outcome_unknown=op == "request_unrated",
                )
            _send_frame(peer, {"ok": True, "kind": "json"}, encoded)
        except PlatformError as exc:
            error = _safe_platform_error(exc)
            self._error(peer, **error)
        except (TimeoutError, socket.timeout):
            self._error(
                peer,
                408,
                "platform RPC request timed out",
                outcome_unknown=op == "request_unrated",
            )
        except _ProtocolError:
            self._error(
                peer,
                400,
                "invalid platform RPC request",
                outcome_unknown=op == "request_unrated",
            )
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            # Exception text may contain a bearer, signed URL, or credential
            # path. Keep journald as sanitized as the browser response.
            _LOG.error("unexpected platform sidecar request failure")
            self._error(
                peer,
                502,
                "FCode platform request failed",
                outcome_unknown=op == "request_unrated",
            )

    @staticmethod
    def _error(
        peer: socket.socket,
        code: int,
        message: str,
        retry_after_s: int | None = None,
        outcome_unknown: bool = False,
    ) -> None:
        try:
            header: dict[str, Any] = {
                "ok": False,
                "code": code,
                "message": message,
            }
            if retry_after_s is not None:
                header["retry_after_s"] = retry_after_s
            if outcome_unknown:
                header["outcome_unknown"] = True
            _send_frame(
                peer,
                header,
                b"",
            )
        except (OSError, _ProtocolError):
            pass


def _prepare_socket(path: str) -> None:
    parent = Path(path).parent
    try:
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"cannot create platform socket directory: {exc}") from exc
    try:
        parent_info = os.stat(parent, follow_symlinks=False)
    except OSError as exc:
        raise RuntimeError("cannot inspect platform socket directory") from exc
    if not stat.S_ISDIR(parent_info.st_mode):
        raise RuntimeError("platform socket parent is not a real directory")
    if parent_info.st_uid != os.geteuid():
        raise RuntimeError("platform socket directory has an untrusted owner")
    if stat.S_IMODE(parent_info.st_mode) & 0o022:
        raise RuntimeError("platform socket directory must not be group/world writable")

    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(info.st_mode):
        raise RuntimeError("refusing to replace a non-socket platform path")
    if info.st_uid != os.geteuid():
        raise RuntimeError("refusing to replace another user's platform socket")
    stale_identity = (info.st_dev, info.st_ino)

    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.settimeout(0.2)
        probe.connect(path)
    except OSError as exc:
        if exc.errno not in {errno.ECONNREFUSED, errno.ENOENT}:
            raise RuntimeError("existing platform socket cannot be safely replaced") from exc
    else:
        raise RuntimeError("another platform sidecar is already running")
    finally:
        probe.close()

    try:
        current = os.lstat(path)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISSOCK(current.st_mode)
        or (current.st_dev, current.st_ino) != stale_identity
    ):
        raise RuntimeError("platform socket changed while checking whether it was stale")
    os.unlink(path)


def _socket_group_id(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("socket group is invalid")
    if isinstance(value, int):
        group_id = value
    elif isinstance(value, str) and value and len(value) <= 128:
        try:
            group_id = grp.getgrnam(value).gr_gid
        except KeyError as exc:
            raise ValueError(f"socket group {value!r} does not exist") from exc
    else:
        raise ValueError("socket group is invalid")
    if group_id < 0:
        raise ValueError("socket group is invalid")
    if (
        os.geteuid() != 0
        and group_id != os.getegid()
        and group_id not in os.getgroups()
    ):
        raise ValueError("sidecar process is not a member of the socket group")
    return group_id


class PlatformSidecarServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    """Threaded Unix server with a hard cap on active request handlers."""

    daemon_threads = True
    block_on_close = True
    request_queue_size = 16
    allow_reuse_address = False

    def __init__(
        self,
        socket_path: str | Path,
        platform: Any | None = None,
        *,
        max_workers: int = _DEFAULT_WORKERS,
        connection_timeout_s: float = _DEFAULT_CONNECTION_TIMEOUT_S,
        socket_group: str | int | None = None,
    ) -> None:
        path = _socket_path(socket_path)
        socket_group_id = _socket_group_id(socket_group)
        if (
            isinstance(max_workers, bool)
            or not isinstance(max_workers, int)
            or not 1 <= max_workers <= _MAX_WORKERS
        ):
            raise ValueError(f"max_workers must be between 1 and {_MAX_WORKERS}")
        timeout = float(connection_timeout_s)
        if not 0.1 <= timeout <= 120.0:
            raise ValueError("connection timeout must be between 0.1 and 120 seconds")

        _prepare_socket(path)
        self.platform = platform if platform is not None else FcodePlatform()
        self.connection_timeout_s = timeout
        self._slots = threading.BoundedSemaphore(max_workers)
        # At most two maximum-size replay bodies are resident/sending at once;
        # the other handler slots remain available for small JSON operations.
        self.replay_slots = threading.BoundedSemaphore(min(2, max_workers))
        self._bound_identity: tuple[int, int] | None = None
        super().__init__(path, _PlatformRpcHandler, bind_and_activate=False)
        try:
            self.server_bind()
            info = os.lstat(path)
            self._bound_identity = (info.st_dev, info.st_ino)
            if socket_group_id is None:
                os.chmod(path, 0o600)
            else:
                os.chown(path, -1, socket_group_id)
                os.chmod(path, 0o660)
            self.server_activate()
        except BaseException:
            super().server_close()
            self._unlink_own_socket()
            raise

    def process_request(self, request: socket.socket, client_address: Any) -> None:
        if not self._slots.acquire(blocking=False):
            try:
                # The matching client has already sent and half-closed its tiny
                # bounded request. Drain it before closing so AF_UNIX delivers
                # the complete 503 frame instead of resetting the connection.
                # A hostile partial request can delay the accept loop by at
                # most 250 ms, never consume a ninth handler thread.
                deadline = time.monotonic() + min(
                    0.25, self.connection_timeout_s
                )
                _recv_frame(
                    request,
                    max_body_bytes=_MAX_REQUEST_BODY_BYTES,
                    deadline=deadline,
                )
                _recv_eof(request, deadline=deadline)
                _send_frame(
                    request,
                    {
                        "ok": False,
                        "code": 503,
                        "message": "FCode platform sidecar is busy",
                    },
                    b"",
                )
            except (OSError, TimeoutError, _ProtocolError):
                # Invalid/silent excess clients are closed without a response.
                # Valid clients always fit in the bounded drain above.
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(
        self, request: socket.socket, client_address: Any
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def server_close(self) -> None:
        try:
            super().server_close()
        finally:
            self._unlink_own_socket()

    def _unlink_own_socket(self) -> None:
        identity = self._bound_identity
        if identity is None:
            return
        try:
            info = os.lstat(self.server_address)
            if (info.st_dev, info.st_ino) == identity and stat.S_ISSOCK(info.st_mode):
                os.unlink(self.server_address)
        except FileNotFoundError:
            pass
        finally:
            self._bound_identity = None


def _positive_workers(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if not 1 <= parsed <= _MAX_WORKERS:
        raise argparse.ArgumentTypeError(f"must be between 1 and {_MAX_WORKERS}")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="serve oarena's bounded FCode platform client over AF_UNIX"
    )
    parser.add_argument("--socket", required=True, help="absolute filesystem socket path")
    parser.add_argument(
        "--workers",
        type=_positive_workers,
        default=_DEFAULT_WORKERS,
        help=f"maximum concurrent requests (default: {_DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=_DEFAULT_CONNECTION_TIMEOUT_S,
        help="per-connection I/O timeout in seconds (default: 20)",
    )
    parser.add_argument(
        "--socket-group",
        help="group allowed to connect (socket mode becomes 0660)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    server = PlatformSidecarServer(
        args.socket,
        max_workers=args.workers,
        connection_timeout_s=args.timeout,
        socket_group=args.socket_group,
    )
    stopping = threading.Event()

    def request_stop(_signum: int, _frame: Any) -> None:
        stopping.set()

    previous = {
        signum: signal.signal(signum, request_stop)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.2},
        name="oarena-platform-sidecar",
        daemon=True,
    )
    try:
        thread.start()
        _LOG.info("platform sidecar listening on %s", server.server_address)
        while thread.is_alive() and not stopping.wait(0.5):
            pass
    finally:
        if thread.is_alive():
            server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
