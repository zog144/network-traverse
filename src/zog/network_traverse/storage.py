"""Local state: exclusive daemon lease, atomic fsynced writes, restrictive mode."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Iterator

from .policy import Policy, PolicyError


class StorageError(RuntimeError):
    pass


class Storage:
    def __init__(self, directory: str | Path = "/state/network-traverse"):
        self.directory = Path(directory)

    def initialize(self) -> None:
        path = self.directory
        if path.is_symlink():
            raise StorageError("state directory may not be a symlink")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not path.is_dir() or path.is_symlink():
            raise StorageError("unsafe state directory")
        os.chmod(path, 0o700)
        if not (path / "policy.json").exists():
            self.write_json("policy.json", Policy.disabled().to_dict())
        if not (path / "leases.json").exists():
            self.write_json("leases.json", {"version": 1, "leases": {}})

    def read_json(self, name: str) -> dict[str, Any]:
        path = self.directory / name
        if path.is_symlink():
            raise StorageError(f"refusing symlink: {name}")
        try:
            with path.open("r", encoding="utf-8") as stream:
                result = json.load(stream)
        except (OSError, ValueError) as exc:
            raise StorageError(f"cannot read {name}: {exc}") from exc
        if not isinstance(result, dict):
            raise StorageError(f"{name} must be a JSON object")
        return result

    def write_json(self, name: str, data: dict[str, Any]) -> None:
        path = self.directory / name
        if path.is_symlink():
            raise StorageError(f"refusing symlink: {name}")
        serialized = json.dumps(data, indent=2, sort_keys=True) + "\n"
        descriptor, temporary = tempfile.mkstemp(prefix=f".{name}.", dir=self.directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def policy(self) -> Policy:
        try:
            return Policy.parse(self.read_json("policy.json"))
        except PolicyError as exc:
            raise StorageError(f"invalid policy: {exc}") from exc

    def leases(self) -> dict[str, dict[str, Any]]:
        data = self.read_json("leases.json")
        if data.get("version") != 1 or not isinstance(data.get("leases"), dict):
            raise StorageError("unsupported leases.json format")
        return data["leases"]

    def save_leases(self, leases: dict[str, dict[str, Any]]) -> None:
        self.write_json("leases.json", {"version": 1, "leases": leases})

    @contextlib.contextmanager
    def daemon_lock(self) -> Iterator[None]:
        path = self.directory / "daemon.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(fd, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise StorageError("another network-traverse daemon owns the state") from exc
            yield
        finally:
            os.close(fd)
