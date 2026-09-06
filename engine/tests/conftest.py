from pathlib import Path

import fitz
import pytest

from app.config import get_settings
from app.store import RunStore


@pytest.fixture
def tmp_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LLM_MOCK", "true")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


@pytest.fixture
def store(tmp_settings):
    return RunStore(tmp_settings)


def make_pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    payload = doc.tobytes()
    doc.close()
    return payload


SAMPLE_POLICY = Path(__file__).parent.parent / "examples" / "sample_policy.txt"
