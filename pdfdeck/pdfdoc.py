"""Shared PyMuPDF document handle.

fitz.Page objects are not graph-serializable, so they never live in LangGraph
state. Instead a PageProvider (cached open documents) is passed through the
run config; nodes fetch pages by index on demand.
"""

from __future__ import annotations

import fitz


class PageProvider:
    def __init__(self) -> None:
        self._docs: dict[str, fitz.Document] = {}

    def doc(self, pdf_path: str) -> fitz.Document:
        if pdf_path not in self._docs:
            self._docs[pdf_path] = fitz.open(pdf_path)
        return self._docs[pdf_path]

    def page(self, pdf_path: str, page_index: int) -> fitz.Page:
        return self.doc(pdf_path)[page_index]

    def close(self) -> None:
        for d in self._docs.values():
            d.close()
        self._docs.clear()
