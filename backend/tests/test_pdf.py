"""Tests for the Markdown→PDF renderer."""

import pytest

from app.infrastructure import pdf as pdf_mod
from app.infrastructure.pdf import render_markdown_pdf


def _font_available() -> bool:
    try:
        pdf_mod._find_font()
        return True
    except RuntimeError:
        return False


pytestmark = pytest.mark.skipif(
    not _font_available(),
    reason="no Unicode TTF font available (install fonts-dejavu-core)",
)


def test_render_markdown_pdf_produces_valid_pdf():
    md = (
        "# Заголовок\n\n"
        "## Подзаголовок\n\n"
        "Параграф с **жирным** текстом и кириллицей.\n\n"
        "- Пункт один\n"
        "- Пункт два\n"
    )
    data = render_markdown_pdf("Тестовый документ", md)
    assert isinstance(data, bytes)
    assert data[:5] == b"%PDF-"
    assert len(data) > 1000


def test_render_markdown_pdf_handles_empty_body():
    data = render_markdown_pdf("Только заголовок", "")
    assert data[:5] == b"%PDF-"
