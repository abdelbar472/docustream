"""Build a short, match-aware excerpt of a chunk for search results.

Naive truncation shows the start of a chunk, which often does not contain the
words the user searched for. Instead we pick the window of the chunk that covers
the most distinct query terms and mark it with ellipses.
"""
import re

_WORD = re.compile(r"[A-Za-z0-9]+")
SNIPPET_WIDTH = 280


def make_snippet(text: str, terms: list[str], width: int = SNIPPET_WIDTH) -> str:
    text = text.strip()
    if not text:
        return ""
    if not terms:
        return _clip(text, 0, width)

    wanted = {t.lower() for t in terms}
    anchors = [m.start() for m in _WORD.finditer(text) if m.group().lower() in wanted]
    if not anchors:
        return _clip(text, 0, width)

    best_start = 0
    best_cover = -1
    for anchor in anchors:
        start = max(0, anchor - width // 3)
        end = min(len(text), start + width)
        cover = len(
            {m.group().lower() for m in _WORD.finditer(text, start, end) if m.group().lower() in wanted}
        )
        if cover > best_cover:
            best_cover, best_start = cover, start

    return _clip(text, best_start, width)


def _clip(text: str, start: int, width: int) -> str:
    end = min(len(text), start + width)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "… " + snippet
    if end < len(text):
        snippet = snippet + " …"
    return snippet
