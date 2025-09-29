from __future__ import annotations

from bs4 import BeautifulSoup
from readability import Document


def extract_readable(html: str) -> tuple[str, str]:
    """
    Returns (title, text) from article HTML.
    """
    doc = Document(html)
    title = doc.short_title()
    summary_html = doc.summary(html_partial=True)
    soup = BeautifulSoup(summary_html, "lxml")
    # get visible text, collapse whitespace
    text = " ".join(soup.get_text(separator=" ").split())
    return title, text
