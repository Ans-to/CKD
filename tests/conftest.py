"""Shared fixtures. Tests are intentionally cheap enough for a free Colab CPU."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    return tmp_path / "projects"


@pytest.fixture(scope="session")
def story():
    from ckd.content.composer import compose_story

    return compose_story("how wifi works", languages=["en", "ur"], target_seconds=45)


@pytest.fixture(scope="session")
def wifi_narration(story):
    """One real narration track (offline espeak), reused by render tests."""
    from ckd.voice.narration import Narrator, SpeechCache

    cache = SpeechCache(Path(os.environ.get("CKD_TEST_CACHE", "/tmp/ckd_test_cache")))
    narrator = Narrator(voice_en="espeak", voice_ur="espeak", cache=cache,
                        allow_download=False)
    return narrator.build(story, "en", fps=24)
