"""Offline wheel/sdist artifact completeness with an extracted-sdist unittest run.

Run after building local packages; never starts the network-traverse daemon.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
LICENSE_FILES = (
    "COPYRIGHT",
    "LICENSE",
    "LICENSES/BSD-3-Clause.txt",
    "LICENSES/GPL-3.0-only.txt",
    "THIRD-PARTY-NOTICES.md",
)
MODULES = tuple(sorted(
    file.relative_to(ROOT / "src").as_posix()
    for file in (ROOT / "src" / "zog" / "network_traverse").glob("*.py")
))
TESTS = (
    "tests/test_mapping_lifecycle.py",
    "tests/test_packets.py",
    "tests/fake_router.py",
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def one(paths: list[pathlib.Path], kind: str) -> pathlib.Path:
    check(len(paths) == 1, f"expected exactly one {kind}, found {len(paths)}")
    return paths[0]


def check_wheel(archive: pathlib.Path) -> None:
    with zipfile.ZipFile(archive) as wheel:
        names = wheel.namelist()
        check(len(names) == len(set(names)), "duplicate wheel members")
        for module in MODULES:
            check(module in names, f"wheel missing {module}")
            check(wheel.read(module) == (ROOT / "src" / module).read_bytes(),
                  f"wheel source mismatch: {module}")
        for legal in LICENSE_FILES:
            matches = [n for n in names if n.endswith("/licenses/" + legal)]
            check(len(matches) == 1, f"wheel missing or duplicate legal file: {legal}")
            check(wheel.read(matches[0]) == (ROOT / legal).read_bytes(),
                  f"wheel legal byte mismatch: {legal}")
        check(not any(name.endswith(".service") or "/recovery/" in name
                      for name in names), "wheel contains deployment/private material")


def check_sdist(archive: pathlib.Path) -> None:
    with tarfile.open(archive, "r:gz") as sdist:
        members = sdist.getmembers()
        names = [member.name for member in members]
        check(len(names) == len(set(names)), "duplicate source members")
        check(all(not member.issym() and not member.islnk() for member in members),
              "source archive contains links")
        roots = {pathlib.PurePosixPath(name).parts[0] for name in names}
        check(len(roots) == 1, "source archive must have one top-level directory")
        root = next(iter(roots))
        for path in MODULES:
            member_name = f"{root}/src/{path}"
            check(member_name in names, f"sdist missing {path}")
            stream = sdist.extractfile(member_name)
            check(stream is not None and stream.read() == (ROOT / "src" / path).read_bytes(),
                  f"sdist module byte mismatch: {path}")
        for path in TESTS:
            member_name = f"{root}/{path}"
            check(member_name in names, f"sdist missing {path}")
            stream = sdist.extractfile(member_name)
            check(stream is not None and stream.read() == (ROOT / path).read_bytes(),
                  f"sdist test byte mismatch: {path}")
        for path in LICENSE_FILES:
            member_name = f"{root}/{path}"
            check(member_name in names, f"sdist missing {path}")
            stream = sdist.extractfile(member_name)
            check(stream is not None and stream.read() == (ROOT / path).read_bytes(),
                  f"sdist legal byte mismatch: {path}")
        check(not any("/recovery/" in name or name.endswith(".service") for name in names),
              "sdist contains deployment/private material")

        # Write only the exact source/tests whose bytes were verified above,
        # rather than extracting arbitrary files or path names from an archive.
        with tempfile.TemporaryDirectory(prefix="nt-sdist-tests-") as temp:
            dest = pathlib.Path(temp)
            for path in MODULES:
                target = dest / "src" / path
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = sdist.extractfile(f"{root}/src/{path}")
                check(stream is not None, f"sdist missing stream: {path}")
                target.write_bytes(stream.read())
            for path in TESTS:
                target = dest / path
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = sdist.extractfile(f"{root}/{path}")
                check(stream is not None, f"sdist missing test stream: {path}")
                target.write_bytes(stream.read())
            env = dict(os.environ)
            env["PYTHONPATH"] = str(dest / "src")
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=dest, env=env, text=True, capture_output=True,
                timeout=90, check=False,
            )
            sys.stdout.write(result.stdout)
            sys.stderr.write(result.stderr)
            check(result.returncode == 0, "extracted sdist tests failed")


def main() -> int:
    check(len(sys.argv) == 2, "usage: check-built-packages.py DIST_DIR")
    dist = pathlib.Path(sys.argv[1])
    check_wheel(one(sorted(dist.glob("*.whl")), "wheel"))
    check_sdist(one(sorted(dist.glob("*.tar.gz")), "source archive"))
    print("Wheel/sdist exact source, legal and extracted test checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
