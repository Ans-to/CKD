"""Acceptance I: cost/privacy — no secrets committed, no hosted AI API anywhere."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"__pycache__", ".git", "projects", "_cache", "models", ".pytest_cache", "samples"}
SECRET_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
]
HOSTED_AI = re.compile(
    r"(api\.openai\.com|api\.anthropic\.com|generativelanguage\.googleapis\.com|"
    r"api\.cohere\.ai|api\.mistral\.ai|api\.replicate\.com|huggingface\.co/api)", re.I)


def _files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in {".mp4", ".wav", ".png", ".jpg", ".ttf", ".onnx", ".zip", ".ipynb"}:
            continue
        if path.stat().st_size > 2_000_000:
            continue
        yield path


def test_no_credentials_in_the_repository():
    hits = []
    for path in _files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                hits.append(f"{path.relative_to(ROOT)} matches {pattern.pattern}")
    assert not hits, "possible credentials committed:\n" + "\n".join(hits)


def test_no_hosted_ai_inference_endpoints():
    hits = []
    for path in _files():
        if path.suffix != ".py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in HOSTED_AI.finditer(text):
            hits.append(f"{path.relative_to(ROOT)}: {match.group(0)}")
    assert not hits, "hosted AI endpoint referenced:\n" + "\n".join(hits)


def test_download_hosts_are_limited_to_model_weights():
    """The only outbound hosts allowed are weight mirrors, never inference APIs."""
    # weight/asset mirrors only — never an inference endpoint
    allowed = {"github.com", "huggingface.co", "objects.githubusercontent.com", "pypi.org",
               "raw.githubusercontent.com"}
    offenders = []
    for path in _files():
        if path.suffix != ".py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for url in re.findall(r"https?://([A-Za-z0-9.\-]+)", text):
            if url in allowed or url.startswith(("127.0.0.1", "0.0.0.0")):
                continue
            if url in {"openfontlicense.org", "github.com"}:
                continue
            offenders.append(f"{path.relative_to(ROOT)}: {url}")
    assert not offenders, "unexpected outbound host:\n" + "\n".join(sorted(set(offenders)))


def test_gitignore_excludes_media_and_models():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("projects/", "_cache/", "models/", "*.wav"):
        assert pattern in text
