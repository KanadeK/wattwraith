"""Build, smoke-test, and checksum the complete release bundle."""

from __future__ import annotations

import hashlib
import shutil
import sys
import tomllib
import zipfile
from pathlib import Path

from _common import ROOT, ensure_within_root, run


def _version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def _digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def main() -> int:
    version = _version()
    output_dir = ensure_within_root(ROOT / "dist-release")
    build_dir = ensure_within_root(ROOT / ".package-build")
    for directory in (output_dir, build_dir):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)

    run([sys.executable, "-m", "build", "--outdir", str(build_dir)])
    run([sys.executable, "scripts/demo.py"])

    wheel = next(build_dir.glob("*.whl"))
    sdist = next(build_dir.glob("*.tar.gz"))
    shutil.copy2(wheel, output_dir / wheel.name)
    shutil.copy2(sdist, output_dir / f"wattwraith-{version}-source-any.tar.gz")
    shutil.copy2(
        ROOT / "site" / "index.html",
        output_dir / f"wattwraith-{version}-static-report-any.html",
    )

    sample_zip = output_dir / f"wattwraith-{version}-sample-data-any.zip"
    with zipfile.ZipFile(sample_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((ROOT / "examples" / "data").iterdir()):
            archive.write(path, arcname=f"data/{path.name}")
        for name in ("annotations.json", "tariff.json", "DATA_LICENSE.md"):
            path = ROOT / "examples" / name
            archive.write(path, arcname=name)

    artifacts = sorted(path for path in output_dir.iterdir() if path.is_file())
    checksum_lines = [f"{_digest(path)}  {path.name}" for path in artifacts]
    (output_dir / "SHA256SUMS.txt").write_text(
        "\n".join(checksum_lines) + "\n",
        encoding="utf-8",
    )
    run([sys.executable, "scripts/clean_install_smoke.py"])
    shutil.rmtree(build_dir)
    print(f"Packaged {len(artifacts)} assets plus SHA256SUMS.txt in {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
