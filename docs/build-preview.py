#!/usr/bin/env python3
"""Render docs/CODELAB.md to docs/preview.html so you can read it as a codelab.

Google's own tool for this is `claat`, which is a Go binary. This produces the
same HTML, using the same `codelab-elements` web components from unpkg, so the
preview looks like the published codelab without anyone installing Go.

    python3 docs/build-preview.py

Every `## ` heading becomes a step. Everything else is ordinary markdown, plus
two things the codelab format adds:

    <aside class="positive">   the green "Developer's Note" boxes
    <aside class="negative">   the amber warnings

Those are written as literal HTML in CODELAB.md and passed straight through.
"""

from __future__ import annotations

import datetime
import html
import pathlib
import re

HERE = pathlib.Path(__file__).parent
SOURCE = HERE / "CODELAB.md"
TARGET = HERE / "preview.html"

CODELAB_ID = "long-running-agent-concert-tickets"
AUTHORS = "Workshop"
DURATION = "120"

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Source+Code+Pro:400,700;Roboto:400,400italic,500,500italic,700,700italic">
  <link rel="stylesheet" href="https://fonts.googleapis.com/icon?family=Material+Icons">
  <link rel="stylesheet" href="https://unpkg.com/codelab-elements/codelab-elements.css">
  <style>
    .success {{
      color: #1e8e3e;
    }}
    code {{
      font-family: 'Source Code Pro', monospace;
    }}
  </style>
</head>
<body class="color-scheme--light">
  <google-codelab id="{id}"
                  title="{title}"
                  authors="{authors}"
                  duration="{duration}"
                  environment="web"
                  feedback-link="">
"""

FOOT = """  </google-codelab>

  <script src="https://unpkg.com/codelab-elements/native-shim.js"></script>
  <script src="https://unpkg.com/codelab-elements/custom-elements.min.js"></script>
  <script src="https://unpkg.com/codelab-elements/prettify.js"></script>
  <script src="https://unpkg.com/codelab-elements/codelab-elements.js"></script>
</body>
</html>
"""


def esc(text: str) -> str:
    """Escape for HTML, matching claat: quotes and apostrophes too."""
    return html.escape(text, quote=True).replace("'", "&#x27;")


def inline(text: str) -> str:
    """Markdown inline spans. Order matters: code first, so nothing rewrites it.

    Code spans are pulled out and replaced with placeholders before anything
    else runs, then put back at the end. Without that, a `**` inside backticks
    turns into a <strong> and the snippet is silently wrong.
    """
    spans: list[str] = []

    def stash(match: re.Match) -> str:
        spans.append(f"<code>{esc(match.group(1))}</code>")
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = esc(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\w)", r"<em>\1</em>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" target="_blank">\1</a>',
        text,
    )
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], text)


def split_row(line: str) -> list[str]:
    r"""Split a table row on unescaped pipes only.

    `\|` is how you put a pipe inside a table cell, and the troubleshooting
    table does exactly that inside a code span (`lsof -ti:8000 \| xargs kill`).
    Splitting naively cuts that cell in half and leaves the backticks unpaired,
    so the shell command renders as literal markdown in the middle of the page.
    """
    cells = re.split(r"(?<!\\)\|", line.strip().strip("|"))
    return [c.strip().replace("\\|", "|") for c in cells]


def render(body: str) -> str:
    """Markdown block elements to claat-flavoured HTML."""
    out: list[str] = []
    lines = body.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # fenced code. Kept verbatim, escaped, never touched by inline rules.
        if line.startswith("```"):
            lang = line[3:].strip()
            i += 1
            block = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            attr = f' class="language-{lang}"' if lang else ""
            out.append(f"<pre><code{attr}>" + esc("\n".join(block)) + "</code></pre>")
            continue

        # literal HTML (the asides, and the odd raw block) passes straight through
        if line.lstrip().startswith(("<aside", "</aside", "<b>", "<img", "<br")):
            out.append(line)
            i += 1
            continue

        # tables
        if line.startswith("|") and i + 1 < len(lines) and re.match(
            r"^\|[\s:|-]+\|$", lines[i + 1]
        ):
            header = split_row(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            head_cells = "".join(f"<th>{inline(h)}</th>" for h in header)
            body_rows = "\n".join(
                "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>"
                for r in rows
            )
            out.append(
                f"<table>\n<thead><tr>{head_cells}</tr></thead>\n"
                f"<tbody>\n{body_rows}\n</tbody>\n</table>"
            )
            continue

        # headings. ### and below only; ## is a step boundary handled by the caller.
        if match := re.match(r"^(#{3,6})\s+(.*)$", line):
            level = len(match.group(1))
            out.append(f"<h{level} is-upgraded>{inline(match.group(2))}</h{level}>")
            i += 1
            continue

        # blockquote
        if line.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip(">").strip())
                i += 1
            out.append(f"<blockquote><p>{inline(' '.join(quote))}</p></blockquote>")
            continue

        # lists
        if re.match(r"^\s*[-*]\s+", line) or re.match(r"^\s*\d+\.\s+", line):
            ordered = bool(re.match(r"^\s*\d+\.\s+", line))
            items = []
            while i < len(lines) and (
                re.match(r"^\s*[-*]\s+", lines[i]) or re.match(r"^\s*\d+\.\s+", lines[i])
            ):
                items.append(re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", lines[i]))
                i += 1
            tag = "ol" if ordered else "ul"
            body_items = "\n".join(f"<li>{inline(x)}</li>" for x in items)
            out.append(f"<{tag}>\n{body_items}\n</{tag}>")
            continue

        # horizontal rule is a step separator in codelab format. Drop it.
        if line.strip() in ("---", "***", "___"):
            i += 1
            continue

        if not line.strip():
            i += 1
            continue

        # paragraph: join until a blank line or a block element starts
        para = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(
            ("```", "|", "#", ">", "<aside", "</aside")
        ) and not re.match(r"^\s*(?:[-*]|\d+\.)\s+", lines[i]):
            para.append(lines[i].strip())
            i += 1
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")

    return "\n".join(out)


def main() -> None:
    text = SOURCE.read_text()

    title_match = re.match(r"^#\s+(.*)$", text.split("\n")[0])
    title = title_match.group(1) if title_match else "Codelab"

    parts = re.split(r"^## (.+)$", text, flags=re.M)
    steps = list(zip(parts[1::2], parts[2::2]))

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    about = (
        f'<google-codelab-about codelab-title="{esc(title)}"\n'
        f'                            authors="{AUTHORS}"\n'
        f'                            last-updated="{stamp}"></google-codelab-about>'
    )

    chunks = [
        HEAD.format(title=esc(title), id=CODELAB_ID, authors=AUTHORS, duration=DURATION)
    ]
    for index, (label, body) in enumerate(steps):
        chunks.append(f'    <google-codelab-step label="{esc(label)}" duration="0">\n')
        if index == 0:
            chunks.append(about + "\n")
        chunks.append(render(body) + "\n")
        chunks.append("    </google-codelab-step>\n")
    chunks.append(FOOT)

    TARGET.write_text("".join(chunks))
    size = TARGET.stat().st_size
    print(f"✓ {TARGET.relative_to(HERE.parent)}  —  {len(steps)} steps, {size:,} bytes")


if __name__ == "__main__":
    main()
