#!/usr/bin/env python3
"""Render CODELAB.md into preview.html — what the codelab looks like in a browser.

    python3 docs/build-preview.py

Run this after every edit to CODELAB.md. There is no other copy of this render,
so a stale preview.html means someone reviews instructions that no longer match
the repo, which is how the waker survived in the docs for a day after it was
deleted from the code.

It writes the same markup Google's `claat` produces, so the page uses the real
codelab-elements stylesheet and looks like the finished thing. `claat` itself is
a Go binary nobody in this workshop needs to install, and this file only has to
handle the markdown that CODELAB.md actually uses:

    # title          the codelab title
    ## step          a step
    ### / #### head  headings inside a step
    ```lang```       fenced code
    | tables |       with a --- separator row
    - / 1.           lists, one level
    > quote          blockquote
    <aside>          passed through untouched, already codelab markup

Anything else — nested lists, images, footnotes — is not used and not supported.
Add it here if the codelab starts using it.
"""

from __future__ import annotations

import datetime
import html
import pathlib
import re
import sys

DOCS = pathlib.Path(__file__).parent
SRC = DOCS / "CODELAB.md"
OUT = DOCS / "preview.html"

PAGE = """<!DOCTYPE html>
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
  <google-codelab id="{cid}"
                  title="{title}"
                  authors="{authors}"
                  duration="{duration}"
                  environment="web"
                  feedback-link="">
{steps}
  </google-codelab>

  <script src="https://unpkg.com/codelab-elements/native-shim.js"></script>
  <script src="https://unpkg.com/codelab-elements/custom-elements.min.js"></script>
  <script src="https://unpkg.com/codelab-elements/prettify.js"></script>
  <script src="https://unpkg.com/codelab-elements/codelab-elements.js"></script>
</body>
</html>
"""


def front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.index("\n---", 3)
    meta = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, text[end + 4 :]


def inline(s: str) -> str:
    """Inline markdown. Code spans are extracted first so their contents are
    never treated as markup — `**` inside a code span is two asterisks."""
    spans: list[str] = []

    def stash(m: re.Match) -> str:
        spans.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(spans) - 1}\x00"

    s = re.sub(r"`([^`]+)`", stash, s)
    s = html.escape(s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\w)", r"<em>\1</em>", s)
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], s)


def render(body: str) -> str:
    """Markdown block elements → HTML. One pass, line by line."""
    out: list[str] = []
    lines = body.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # fenced code — verbatim, no inline processing
        if line.startswith("```"):
            lang = line[3:].strip()
            i += 1
            code = []
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            attr = f' class="language-{lang}"' if lang else ""
            out.append(f"<pre><code{attr}>{html.escape(chr(10).join(code))}\n</code></pre>")
            continue

        # raw html (asides, diagrams in <p>) passes straight through
        if line.lstrip().startswith("<"):
            out.append(line)
            i += 1
            continue

        # table — needs the --- separator on the next line to count
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            def cells(row: str) -> list[str]:
                return [c.strip() for c in row.strip().strip("|").split("|")]

            head = cells(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            out.append("<table>")
            out.append("<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead>")
            out.append("<tbody>")
            for r in rows:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table>")
            continue

        # lists
        if re.match(r"^\s*[-*] ", line) or re.match(r"^\s*\d+\. ", line):
            ordered = bool(re.match(r"^\s*\d+\. ", line))
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>")
            while i < len(lines) and (
                re.match(r"^\s*[-*] ", lines[i]) or re.match(r"^\s*\d+\. ", lines[i])
            ):
                item = re.sub(r"^\s*(?:[-*]|\d+\.) ", "", lines[i])
                i += 1
                # continuation lines are indented under the marker
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip() \
                        and not re.match(r"^\s*(?:[-*]|\d+\.) ", lines[i]):
                    item += " " + lines[i].strip()
                    i += 1
                out.append(f"<li>{inline(item)}</li>")
            out.append(f"</{tag}>")
            continue

        # blockquote
        if line.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip(">").strip())
                i += 1
            out.append(f"<blockquote><p>{inline(' '.join(quote))}</p></blockquote>")
            continue

        # headings inside a step
        m = re.match(r"^(#{3,6}) (.+)$", line)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level} is-upgraded>{inline(m.group(2))}</h{level}>")
            i += 1
            continue

        if not line.strip():
            i += 1
            continue

        # paragraph — runs until a blank line or the start of another block
        para = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(("```", "|", ">", "#")) \
                and not lines[i].lstrip().startswith("<") \
                and not re.match(r"^\s*(?:[-*]|\d+\.) ", lines[i]):
            para.append(lines[i].strip())
            i += 1
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")

    return "\n".join(out)


def main() -> int:
    meta, body = front_matter(SRC.read_text())

    title_match = re.search(r"^# (.+)$", body, re.M)
    title = title_match.group(1).strip() if title_match else "Codelab"
    body = body[title_match.end() :] if title_match else body

    # split on ## — each one is a step
    parts = re.split(r"^## (.+)$", body, flags=re.M)[1:]
    if not parts:
        print("✗ no '## ' steps found in CODELAB.md", file=sys.stderr)
        return 1

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    steps = []
    for n, (label, content) in enumerate(zip(parts[::2], parts[1::2])):
        inner = render(content.strip())
        if n == 0:
            inner = (
                f'<google-codelab-about codelab-title="{html.escape(title)}"\n'
                f'                            authors="{meta.get("authors", "Workshop")}"\n'
                f'                            last-updated="{stamp}"></google-codelab-about>\n'
                + inner
            )
        steps.append(
            f'    <google-codelab-step label="{html.escape(label.strip())}" duration="0">\n'
            f"{inner}\n"
            f"    </google-codelab-step>\n"
        )

    OUT.write_text(
        PAGE.format(
            title=html.escape(title),
            cid=meta.get("id", "codelab"),
            authors=meta.get("authors", "Workshop"),
            duration=meta.get("duration", "120"),
            steps="\n".join(steps),
        )
    )
    print(f"✓ {OUT.relative_to(DOCS.parent)}  —  {len(steps)} steps, {len(OUT.read_text()):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
