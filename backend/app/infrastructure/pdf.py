"""Render Markdown documents to simple, Cyrillic-capable PDFs.

fpdf2's built-in fonts are latin-1 only, so we register a Unicode TTF. The font
is discovered from a list of candidate paths — DejaVu on the Debian-based Docker
image (installed via ``fonts-dejavu-core``), Arial Unicode on macOS for local
runs. Markdown is rendered with light styling: ``#``/``##`` headings, ``-``/``*``
bullet lists, and inline ``**bold**`` markers are stripped; everything else
becomes a paragraph. The goal is a clean, readable downloadable PDF — not a
pixel-perfect mirror of the in-app rendering.
"""
from __future__ import annotations

import os
import re

# (regular, bold) candidate paths, tried in order. bold is optional.
_FONT_CANDIDATES: list[tuple[str, str | None]] = [
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", None),
    ("/Library/Fonts/Arial Unicode.ttf", None),
]


def _find_font() -> tuple[str, str | None]:
    for regular, bold in _FONT_CANDIDATES:
        if os.path.exists(regular):
            return regular, (bold if bold and os.path.exists(bold) else None)
    raise RuntimeError(
        "No Unicode TTF font found for PDF generation. "
        "Install fonts-dejavu-core (Debian) or provide a Unicode font."
    )


def _strip_inline(text: str) -> str:
    """Drop Markdown emphasis markers — the PDF renders plain text runs."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    return text


def render_markdown_pdf(title: str, markdown: str) -> bytes:
    """Render ``title`` + Markdown ``markdown`` into PDF bytes."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    regular, bold = _find_font()
    bold_style = "B" if bold else ""

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(20, 20, 20)
    pdf.add_page()
    pdf.add_font("doc", "", regular)
    if bold:
        pdf.add_font("doc", "B", bold)

    # Always return the cursor to the left margin and advance to the next line —
    # fpdf2's multi_cell default leaves x at the right edge, which then makes the
    # next full-width cell compute ~0 usable width and raise.
    def block(h: float, text: str) -> None:
        pdf.multi_cell(0, h, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("doc", bold_style, 18)
    block(9, title)
    pdf.ln(3)

    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            pdf.ln(3)
            continue
        if line.startswith("## "):
            pdf.set_font("doc", bold_style, 13)
            block(7, _strip_inline(line[3:].strip()))
        elif line.startswith("# "):
            pdf.set_font("doc", bold_style, 15)
            block(8, _strip_inline(line[2:].strip()))
        elif line[:2] in ("- ", "* "):
            pdf.set_font("doc", "", 11)
            block(6, f"-  {_strip_inline(line[2:].strip())}")
        else:
            pdf.set_font("doc", "", 11)
            block(6, _strip_inline(line))

    return bytes(pdf.output())
