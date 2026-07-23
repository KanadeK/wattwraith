"""Install the built wheel without checkout imports and test its CLI metadata."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import venv
import zipfile

from _common import ROOT, ensure_within_root, task_environment

REQUIRED_FINDINGS = {"baseline", "periodic_standby", "overnight_sustained"}


def main() -> int:
    wheels = sorted((ROOT / "dist-release").glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"Expected one release wheel, found {len(wheels)}")
    sample_archives = sorted((ROOT / "dist-release").glob("*-sample-data-any.zip"))
    if len(sample_archives) != 1:
        raise SystemExit(f"Expected one sample archive, found {len(sample_archives)}")
    smoke_root = ensure_within_root(ROOT / ".release-tmp")
    if smoke_root.exists():
        shutil.rmtree(smoke_root)
    smoke_root.mkdir(parents=True)
    environment = task_environment()
    try:
        environment_dir = smoke_root / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment_dir)
        python = (
            environment_dir / "Scripts" / "python.exe"
            if sys.platform == "win32"
            else environment_dir / "bin" / "python"
        )
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                str(wheels[0]),
            ],
            cwd=smoke_root,
            env=environment,
            check=True,
        )
        result = subprocess.run(
            [str(python), "-m", "wattwraith.cli", "--version"],
            cwd=smoke_root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        if "wattwraith " not in result.stdout.lower():
            raise SystemExit(f"Unexpected installed CLI output: {result.stdout!r}")
        print(result.stdout.strip())
        sample_dir = smoke_root / "sample"
        with zipfile.ZipFile(sample_archives[0]) as archive:
            archive.extractall(sample_dir)
        output_dir = smoke_root / "report"
        analysis = subprocess.run(
            [
                str(python),
                "-m",
                "wattwraith.cli",
                "analyze",
                str(sample_dir / "data" / "smart_plug_week.csv"),
                "--annotations",
                str(sample_dir / "annotations.json"),
                "--tariff",
                str(sample_dir / "tariff.json"),
                "--output-dir",
                str(output_dir),
            ],
            cwd=smoke_root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        summary = json.loads(analysis.stdout)
        if summary["devices"] != 4:
            raise SystemExit(f"Installed CLI analyzed {summary['devices']} devices, expected 4")
        payload = json.loads((output_dir / "wattwraith-report.json").read_text(encoding="utf-8"))
        detected = {
            result["kind"]
            for report in payload["reports"]
            for result in report["results"]
            if result["status"] == "detected"
        }
        missing = REQUIRED_FINDINGS.difference(detected)
        if missing:
            raise SystemExit(f"Installed CLI did not detect required findings: {sorted(missing)}")
        print("Clean installed wheel analyzed the release sample successfully")
    finally:
        if smoke_root.exists():
            shutil.rmtree(smoke_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
