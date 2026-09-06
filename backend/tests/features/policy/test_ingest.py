import hashlib
from pathlib import Path

import pytest

from app.domain.models import PolicyPage
from app.features.policy.ingest import (
    MAX_PDF_PAGES,
    MAX_POLICY_CHARS,
    PolicyIngestionError,
    ingest_policy_text,
    ingest_policy_pages,
    load_bundled_policy,
    load_bundled_policy_text,
    prepare_policy_pages,
    prepare_policy_text,
    to_policy_pages,
)


def test_prepare_policy_text_normalizes_unicode_and_newlines() -> None:
    prepared = prepare_policy_text("Caf\u00e9\r\nreceipt e\u0301vidence")

    assert prepared.text == "Caf\u00e9\nreceipt \u00e9vidence"
    assert prepared.character_count == len(prepared.text)
    assert len(prepared.pages) == 1
    assert prepared.pages[0].page_number == 1
    assert prepared.pages[0].start_offset == 0
    assert prepared.pages[0].end_offset == len(prepared.text)


@pytest.mark.parametrize("text", ["", "   ", "\n\t\r"])
def test_prepare_policy_text_rejects_empty_or_whitespace_input(text: str) -> None:
    with pytest.raises(PolicyIngestionError, match="EMPTY_POLICY"):
        prepare_policy_text(text)


def test_prepare_policy_text_accepts_exact_character_limit() -> None:
    prepared = prepare_policy_text("a" * MAX_POLICY_CHARS)

    assert prepared.character_count == MAX_POLICY_CHARS


def test_prepare_policy_text_rejects_text_over_character_limit() -> None:
    with pytest.raises(PolicyIngestionError, match="POLICY_TOO_LARGE"):
        prepare_policy_text("a" * (MAX_POLICY_CHARS + 1))


def test_prepare_policy_pages_assigns_deterministic_global_offsets() -> None:
    prepared = prepare_policy_pages(("First page\r\nline", "Second e\u0301 page"))

    assert [page.text for page in prepared.pages] == [
        "First page\nline",
        "Second \u00e9 page",
    ]
    assert prepared.text == "First page\nline\nSecond \u00e9 page"
    assert prepared.pages[0].start_offset == 0
    assert prepared.pages[0].end_offset == len("First page\nline")
    assert prepared.pages[1].start_offset == len("First page\nline") + 1
    assert prepared.pages[1].end_offset == len(prepared.text)


def test_prepared_pages_map_to_person_1_policy_page_contract() -> None:
    prepared = prepare_policy_pages(("First page", "Second page"))

    pages = to_policy_pages(prepared)

    assert pages == (
        PolicyPage(page=1, text="First page", start=0, end=10),
        PolicyPage(page=2, text="Second page", start=11, end=22),
    )
    assert all(isinstance(page, PolicyPage) for page in pages)


def test_ingest_policy_text_builds_deterministic_contract_document() -> None:
    document = ingest_policy_text(
        title="Cafe policy",
        text="Café\r\nreceipt e\u0301vidence",
        source_type="pasted_text",
    )
    normalized = "Café\nreceipt évidence"

    assert document.pages == (
        PolicyPage(page=1, text=normalized, start=0, end=len(normalized)),
    )
    assert document.document_sha256 == hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()
    assert document.document_id == f"document-{document.document_sha256}"


def test_document_content_identity_ignores_title_and_source_label() -> None:
    pasted = ingest_policy_text(
        title="First title",
        text="Receipts required.",
        source_type="pasted_text",
    )
    bundled = ingest_policy_text(
        title="Second title",
        text="Receipts required.",
        source_type="bundled_sample",
    )

    assert pasted.document_sha256 == bundled.document_sha256
    assert pasted.document_id == bundled.document_id


def test_ingest_policy_text_rejects_unsupported_source_type() -> None:
    with pytest.raises(PolicyIngestionError, match="UNSUPPORTED_SOURCE_TYPE"):
        ingest_policy_text(
            title="Policy",
            text="Receipts required.",
            source_type="pdf",  # type: ignore[arg-type]
        )


def test_load_bundled_policy_builds_contract_document(tmp_path: Path) -> None:
    path = tmp_path / "development-policy.txt"
    path.write_text("Receipts\r\nrequired.", encoding="utf-8")

    document = load_bundled_policy(path)

    assert document.title == "development-policy"
    assert document.source_type == "bundled_sample"
    assert document.pages[0].text == "Receipts\nrequired."


def test_ingest_policy_pages_preserves_global_offsets_and_content_hash() -> None:
    document = ingest_policy_pages(
        title="Two-page policy",
        pages=("First page", "Second page"),
        source_type="bundled_sample",
    )

    assert [(page.start, page.end) for page in document.pages] == [(0, 10), (11, 22)]
    assert document.document_sha256 == hashlib.sha256(
        b"First page\nSecond page"
    ).hexdigest()


def test_prepare_policy_pages_rejects_too_many_pages() -> None:
    with pytest.raises(PolicyIngestionError, match="TOO_MANY_PAGES"):
        prepare_policy_pages(tuple("page" for _ in range(MAX_PDF_PAGES + 1)))


def test_prepare_policy_pages_rejects_blank_page() -> None:
    with pytest.raises(PolicyIngestionError, match="EMPTY_PAGE"):
        prepare_policy_pages(("Page one", "  \n"))


def test_load_bundled_policy_text_reads_and_normalizes_utf8(tmp_path: Path) -> None:
    path = tmp_path / "policy.txt"
    path.write_text("Caf\u00e9\r\nreceipts required", encoding="utf-8")

    prepared = load_bundled_policy_text(path)

    assert prepared.text == "Caf\u00e9\nreceipts required"


def test_load_bundled_policy_text_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(PolicyIngestionError, match="POLICY_FILE_NOT_FOUND"):
        load_bundled_policy_text(tmp_path / "missing.txt")


def test_load_bundled_policy_text_sanitizes_decode_error(tmp_path: Path) -> None:
    path = tmp_path / "private-policy.txt"
    path.write_bytes(b"\xff\xfe")

    with pytest.raises(PolicyIngestionError) as exc_info:
        load_bundled_policy_text(path)

    assert "INVALID_UTF8" in str(exc_info.value)
    assert "private-policy" not in str(exc_info.value)
