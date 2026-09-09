from __future__ import annotations

from ats_matcher.extract.text import LOW_TEXT_THRESHOLD, extract_document


def test_digital_pdf_is_nonempty(digital_pdf):
    doc = extract_document(digital_pdf)
    assert doc.quality == "ok"
    assert doc.char_count > LOW_TEXT_THRESHOLD
    assert "Maya Chen" in doc.text
    assert "FastAPI" in doc.text
    assert doc.source in {"pdfplumber", "pypdf"}


def test_two_column_pdf_keeps_both_sides(two_column_pdf):
    doc = extract_document(two_column_pdf)
    assert "LEFTUNIQUE" in doc.text
    assert "RIGHTUNIQUE" in doc.text
    assert "Omar Haddad" in doc.text


def test_multipage_pdf_has_page_markers(multipage_pdf):
    doc = extract_document(multipage_pdf)
    assert "--- page 1 ---" in doc.text
    assert "--- page 2 ---" in doc.text
    assert "PageOneBody ALPHA" in doc.text
    assert "PageTwoBody BETA" in doc.text
    # Repeated header/footer should be stripped when present on every page.
    assert doc.text.count("HeaderRepeat") <= 1


def test_low_text_pdf_marked_low(low_text_pdf):
    doc = extract_document(low_text_pdf)
    assert doc.quality == "low"
    assert doc.char_count < LOW_TEXT_THRESHOLD


def test_docx_extraction(sample_docx):
    doc = extract_document(sample_docx)
    assert doc.source == "docx"
    assert "Priya Nair" in doc.text
    assert "pandas" in doc.text
    assert "priya.nair@example.com" in doc.text
