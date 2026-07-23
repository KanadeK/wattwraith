"""Fail-closed v0.1.0 release readiness gate."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tomllib

from _common import ROOT, run

EXPECTED_VERSION = "0.1.0"
REQUIRED_FINDINGS = {"baseline", "periodic_standby", "overnight_sustained"}


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", *arguments],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def _check_clean() -> None:
    status = _git("status", "--porcelain")
    if status:
        raise SystemExit(f"Release check requires a clean worktree:\n{status}")


def _check_versions() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        package_version = str(tomllib.load(handle)["project"]["version"])
    namespace: dict[str, str] = {}
    exec((ROOT / "src" / "wattwraith" / "__init__.py").read_text(), namespace)
    if package_version != EXPECTED_VERSION or namespace["__version__"] != EXPECTED_VERSION:
        raise SystemExit("Package metadata and runtime version must both be 0.1.0")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if "## [0.1.0]" not in changelog:
        raise SystemExit("CHANGELOG.md has no v0.1.0 release section")
    for readme in ("README.md", "README.zh-CN.md"):
        if "v0.1.0" not in (ROOT / readme).read_text(encoding="utf-8"):
            raise SystemExit(f"{readme} does not state v0.1.0")


def _check_forbidden_markers() -> None:
    markers = ("TO" + "DO", "FIX" + "ME", "Not" + "Implemented", "place" + "holder")
    tracked = _git("ls-files").splitlines()
    findings: list[str] = []
    for filename in tracked:
        path = ROOT / filename
        if path.suffix.lower() in {".png", ".gif", ".zip", ".gz", ".whl"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in markers:
            if marker.lower() in text.lower():
                findings.append(f"{filename}: {marker}")
    if findings:
        raise SystemExit("Forbidden shell markers found:\n" + "\n".join(findings))


def _check_secrets() -> None:
    patterns = (
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    )
    for filename in _git("ls-files").splitlines():
        path = ROOT / filename
        if b"\0" in path.read_bytes():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in patterns):
            raise SystemExit(f"Potential secret found in {filename}")


def _check_authors() -> None:
    expected_name = _git("config", "--local", "--get", "user.name")
    expected_email = _git("config", "--local", "--get", "user.email")
    identities = _git("log", "--format=%an|%ae|%cn|%ce").splitlines()
    expected = f"{expected_name}|{expected_email}|{expected_name}|{expected_email}"
    unexpected = [identity for identity in identities if identity != expected]
    if unexpected:
        raise SystemExit("Unexpected author or committer:\n" + "\n".join(unexpected))
    if "co-authored-by:" in _git("log", "--format=%B").lower():
        raise SystemExit("Co-authored-by trailers are not allowed")


def _check_demo() -> None:
    payload = json.loads((ROOT / "site" / "report.json").read_text(encoding="utf-8"))
    detected: set[str] = set()
    for report in payload["reports"]:
        for result in report["results"]:
            if not result["evidence"] or "score" not in result["confidence"]:
                raise SystemExit("A demo finding lacks evidence or confidence")
            if result["status"] == "detected":
                detected.add(result["kind"])
    missing = REQUIRED_FINDINGS.difference(detected)
    if missing:
        raise SystemExit(f"Demo did not detect required patterns: {sorted(missing)}")


def _check_artifacts() -> None:
    output_dir = ROOT / "dist-release"
    checksum_path = output_dir / "SHA256SUMS.txt"
    if not checksum_path.is_file():
        raise SystemExit("SHA256SUMS.txt is missing")
    lines = checksum_path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 4:
        raise SystemExit("Release bundle is incomplete")
    for line in lines:
        expected, filename = line.split("  ", 1)
        path = output_dir / filename
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"Release asset missing or empty: {filename}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f"Checksum mismatch: {filename}")


def main() -> int:
    _check_clean()
    _check_versions()
    _check_forbidden_markers()
    _check_secrets()
    _check_authors()
    run([sys.executable, "scripts/verify.py"])
    run([sys.executable, "scripts/package_release.py"])
    _check_demo()
    _check_artifacts()
    _check_clean()
    print("Release check passed: source, tests, authors, demo, and artifacts are verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
