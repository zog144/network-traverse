"""Fail closed on unexpected generated/operational files in public source."""
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "LICENSE", "COPYRIGHT", "LICENSES/BSD-3-Clause.txt",
    "LICENSES/GPL-3.0-only.txt", "THIRD-PARTY-NOTICES.md",
    "pyproject.toml", "src/zog/network_traverse/__init__.py",
    "tests/test_mapping_lifecycle.py", "tests/test_packets.py",
    "tests/fake_router.py", "MANIFEST.in", "tools/check-built-packages.py",
    ".github/workflows/source-only.yml",
}
FORBIDDEN_SEGMENTS = {
    "recovery", "private", "state", "node_modules", "dist", ".venv",
    "__pycache__", ".aws", ".ssh", ".git", ".version-share",
}
FORBIDDEN_EXTENSIONS = {
    ".whl", ".egg", ".pyc", ".p12", ".pfx", ".pem", ".key",
    ".db", ".sqlite", ".sqlite3", ".zip", ".tar", ".tgz",
}

def main():
    tracked = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "-s", "-z"]
    ).decode("utf-8").split("\0")
    entries = {}
    errors = []
    for line in filter(None, tracked):
        meta, path = line.split("\t", 1)
        mode, _sha, stage = meta.split()
        entries[path] = mode
        rel = Path(path)
        if mode != "100644" or stage != "0":
            errors.append(("unsafe-mode", path))
        if any(p in FORBIDDEN_SEGMENTS for p in rel.parts):
            errors.append(("operational-path", path))
        if rel.suffix.lower() in FORBIDDEN_EXTENSIONS:
            errors.append(("binary-or-secret-artifact", path))
        file = ROOT / path
        if not file.is_file() or file.is_symlink():
            errors.append(("symlink-or-missing", path))
            continue
        body = file.read_bytes()
        if b"\0" in body:
            errors.append(("NUL-byte", path))
        try:
            body.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(("non-UTF8", path))
    for p in sorted(REQUIRED - entries.keys()):
        errors.append(("missing", p))
    for p in ("LICENSE", "COPYRIGHT", "pyproject.toml"):
        if p in entries and "BSD-3-Clause OR GPL-3.0-only" not in (
            ROOT / p
        ).read_text():
            errors.append(("missing-dual-license", p))
    if "MANIFEST.in" in entries:
        manifest = (ROOT / "MANIFEST.in").read_text()
        if "recursive-include tests *.py" not in manifest:
            errors.append(("missing-test-fixture-packaging-rule", "MANIFEST.in"))
    if "pyproject.toml" in entries:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())
        if "COPYRIGHT" not in project.get("project", {}).get("license-files", []):
            errors.append(("missing-copyright-license-delivery", "pyproject.toml"))
        if project.get("project", {}).get("name") != "zog-network-traverse":
            errors.append(("wrong-package", "pyproject.toml"))
        if project.get("project", {}).get("dependencies") != []:
            errors.append(("unexpected-runtime-dependency", "pyproject.toml"))
    # Source-only repo may not declare a service or privilege grant.
    if any(path.endswith((".service", ".timer", ".socket"))
           for path in entries):
        errors.append(("native-activation-must-be-separate", "<unit>"))
    print("Source-only tracked files:", len(entries))
    for label, p in errors:
        print("SOURCE-EXPORT-HOLD:", label, p)
    return int(bool(errors))

if __name__ == "__main__":
    sys.exit(main())
