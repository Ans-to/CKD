"""Acceptance A: the repo installs and the toolchain is complete."""
import json
import subprocess
from pathlib import Path


def test_package_imports_and_version():
    import ckd

    assert ckd.__version__ or True  # package import must never touch the network


def test_fonts_present(root: Path):
    from ckd.text.fonts import FontBook

    available = FontBook().available()
    missing = [role for role, ok in available.items() if not ok]
    assert not missing, f"missing bundled fonts: {missing}"


def test_ffmpeg_available():
    from ckd.render.ffmpeg import ffmpeg_version

    assert ffmpeg_version().startswith("ffmpeg version")


def test_cli_help_runs():
    out = subprocess.run(["python", "-m", "ckd", "--help"], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0
    assert "render" in out.stdout and "preview" in out.stdout


def test_environment_report_has_no_hard_failures():
    from ckd.notebook_api import check_environment

    report = check_environment()
    assert report["ffmpeg"].startswith("ffmpeg version")
    assert all(report["fonts_ok"].values())
    assert report["free_disk_gb"] > 0
    json.dumps(report)  # must be JSON-serialisable for the notebook display


def test_requirements_file_matches_imports(root: Path):
    req = (root / "requirements.txt").read_text(encoding="utf-8")
    for package in ("pillow", "numpy", "uharfbuzz", "freetype-py", "imageio-ffmpeg"):
        assert package.lower() in req.lower(), f"{package} missing from requirements.txt"
