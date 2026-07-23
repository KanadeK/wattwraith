from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_github_configuration_is_valid_yaml() -> None:
    paths = sorted((ROOT / ".github").rglob("*.yml"))
    assert len(paths) >= 8
    for path in paths:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict), path


def test_workflows_fail_closed_and_use_declared_task_scripts() -> None:
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    )
    assert "continue-on-error" not in workflow_text
    for script in ("verify.py", "demo.py", "package_release.py", "release_check.py"):
        assert f"scripts/{script}" in workflow_text
        assert (ROOT / "scripts" / script).is_file()


def test_security_release_and_pages_workflows_cover_known_hosting_constraints() -> None:
    security = (ROOT / ".github" / "workflows" / "security.yml").read_text(encoding="utf-8")
    assert "--no-emit-project" in security
    assert "--requirement" in security
    assert "--disable-pip" in security

    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert 'git config --local user.name "KanadeK"' in release
    assert "121669563+KanadeK@users.noreply.github.com" in release

    pages = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "pages: write" in pages
    assert "id-token: write" in pages


def test_ci_clean_installs_release_assets_on_every_matrix_runner() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    matrix_step = "Build and clean-install release-shaped assets"
    assert matrix_step in ci
    assert ci.index(matrix_step) < ci.index("runner.os == 'Linux'")


def test_makefile_exposes_real_cross_platform_targets() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    for target, script in (
        ("verify:", "scripts/verify.py"),
        ("demo:", "scripts/demo.py"),
        ("package:", "scripts/package_release.py"),
        ("release-check:", "scripts/release_check.py"),
    ):
        assert target in makefile
        assert script in makefile
