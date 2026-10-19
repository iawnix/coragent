"""Extract inline Markdown link destinations outside code, using only stdlib."""
from __future__ import annotations

import re


_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_BACKTICKS = re.compile(r"`+")


def _blank(text: str) -> str:
    # Keep line boundaries and character positions for the subsequent scan.
    return re.sub(r"[^\r\n]", " ", text)


def _without_code(text: str) -> str:
    lines = []
    fence = None
    for line in text.splitlines(keepends=True):
        match = _FENCE.match(line.rstrip("\r\n"))
        if fence is not None:
            lines.append(_blank(line))
            if (match and match[1][0] == fence[0] and len(match[1]) >= len(fence)
                    and not match[2].strip()):
                fence = None
        elif match and (match[1][0] == "~" or "`" not in match[2]):
            fence = match[1]
            lines.append(_blank(line))
        else:
            lines.append(line)
    # Code spans cannot join separate paragraphs (or cross a masked fence).
    return "".join(_without_code_spans(part)
                   for part in re.split(r"(\n[ \t]*\n)", "".join(lines)))


def _without_code_spans(text: str) -> str:
    spans = list(_BACKTICKS.finditer(text))
    masked = list(text)
    index = 0
    while index < len(spans):
        opening = spans[index]
        before = text[:opening.start()]
        escapes = len(before) - len(before.rstrip("\\"))
        if escapes % 2:
            index += 1
            continue
        # CommonMark code spans close on a run of exactly the same length.
        closing = next((end for end in range(index + 1, len(spans))
                        if spans[end].group() == opening.group()), None)
        if closing is None:
            index += 1
            continue
        start, end = opening.start(), spans[closing].end()
        masked[start:end] = _blank(text[start:end])
        index = closing + 1
    return "".join(masked)


def markdown_links(text: str) -> list[str]:
    """Return inline link/image targets, preserving code-formatted link labels.

    Code spans and backtick/tilde fenced blocks contain examples, not links.
    Unmatched inline backticks remain ordinary text.
    """
    return _LINK.findall(_without_code(text))
