"""Read-only local Unix socket with optional supervised reconcile ticks."""

from __future__ import annotations

import json
import logging
import os
import socket
import stat
import time
from pathlib import Path
from typing import Callable

from .agent import Agent

LOG = logging.getLogger(__name__)


class InspectServer:
    def __init__(self, agent: Agent, socket_path: str | Path):
        self.agent = agent
        self.path = Path(socket_path)

    def serve_forever(self, *, interval_seconds: float = 30,
                      clock: Callable[[], float] = time.monotonic) -> None:
        if interval_seconds < 1:
            raise ValueError("reconcile interval must be at least one second")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise RuntimeError("refusing symlink at inspect socket path")
        if self.path.exists():
            if not stat.S_ISSOCK(self.path.lstat().st_mode):
                raise RuntimeError("existing API path is not a socket")
            self.path.unlink()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(self.path))
            os.chmod(self.path, 0o600)
            listener.listen(8)
            next_tick = clock()
            try:
                while True:
                    if clock() >= next_tick:
                        try:
                            self.agent.reconcile()
                        except Exception:
                            # State remains durable, and a failed router call
                            # must not terminate the inspect service.
                            LOG.exception("reconcile failed; will retry")
                        next_tick = clock() + interval_seconds
                    listener.settimeout(min(1.0, max(0.01, next_tick - clock())))
                    try:
                        connection, _ = listener.accept()
                    except socket.timeout:
                        continue
                    with connection:
                        connection.settimeout(3)
                        try:
                            query = json.loads(connection.recv(4096).split(b"\n", 1)[0])
                            result = (self.agent.inspect() if query == {"operation": "inspect"}
                                      else {"error": "unsupported operation"})
                        except (ValueError, OSError, RuntimeError) as exc:
                            result = {"error": str(exc)}
                        connection.sendall((json.dumps(result, sort_keys=True) + "\n").encode())
            finally:
                self.path.unlink(missing_ok=True)
