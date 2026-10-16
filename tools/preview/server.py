#!/usr/bin/env python3
"""Preview server for the Base44 sandbox.

This repository is a Claude Code skill pack: Markdown only, no application, so
nothing listens on the sandbox preview port. This small stdlib server gives the
preview a real web entry point on port 3000 by rendering the repository's own
Markdown — README, docs/, examples/, tests/ and every SKILL.md — plus a
filterable index of all skills.

Content is read on every request, so edits appear on reload. Pages poll /__rev
and reload themselves when a Markdown file changes, which is this repo's
stand-in for a dev server's live reload.
"""

from __future__ import annotations

import html
import mimetypes
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import markdown

ROOT = Path(__file__).resolve().parents[2]
PORT = int(os.environ.get("PREVIEW_PORT", "3000"))

SKILL_DIRS = (".claude/skills", "skills")
DOC_DIRS = ("docs", "examples", "tests")
DOC_FILES = ("README.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md")

FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
FIELD = re.compile(r"^(\w+):\s*(.*)$", re.M)
MD_HREF = re.compile(r'href="([^"#?]+\.md)([^"]*)"')

CSS = """
:root { color-scheme: light dark; --ink: #1c1a17; --dim: #6b6459; --bg: #fbf9f5; --line: #e2ddd3; --accent: #7a4a1d; }
@media (prefers-color-scheme: dark) {
  :root { --ink: #ece7df; --dim: #a49b8d; --bg: #15130f; --line: #322c24; --accent: #d9a06a; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); overflow-wrap: break-word;
  font: 16px/1.65 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
header { display: flex; gap: .75rem; align-items: baseline; padding: 1.1rem clamp(1rem, 5vw, 3rem);
  border-bottom: 1px solid var(--line); }
header a { color: var(--ink); font-weight: 700; text-decoration: none; letter-spacing: -0.01em; }
header span { color: var(--dim); font-size: .9rem; }
main { max-width: 62rem; margin: 0 auto; padding: 2rem clamp(1rem, 5vw, 3rem) 5rem; }
h1 { font-size: 1.7rem; letter-spacing: -0.02em; }
h2 { margin-top: 2.5rem; font-size: 1.1rem; text-transform: uppercase; letter-spacing: .08em; color: var(--dim); }
h2 small { text-transform: none; letter-spacing: 0; font-weight: 400; }
input[type=search] { width: 100%; margin-top: 1rem; padding: .7rem .9rem; font: inherit;
  color: inherit; background: transparent; border: 1px solid var(--line); border-radius: .5rem; }
ul { list-style: none; padding: 0; }
ul.docs li { padding: .35rem 0; border-bottom: 1px solid var(--line); }
ul.skills li { padding: .8rem 0; border-bottom: 1px solid var(--line); }
ul.skills a { font-weight: 600; }
ul.skills p { margin: .25rem 0 0; color: var(--dim); font-size: .92rem; }
a { color: var(--accent); }
article.md { max-width: 52rem; }
article.md pre { overflow-x: auto; overflow-wrap: normal; padding: .9rem 1rem; border: 1px solid var(--line); border-radius: .5rem; }
article.md code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .9em; }
article.md table { border-collapse: collapse; width: 100%; display: block; overflow-x: auto; }
article.md th, article.md td { border: 1px solid var(--line); padding: .4rem .6rem; text-align: left; }
article.md blockquote { margin: 1rem 0; padding-left: 1rem; border-left: 3px solid var(--line); color: var(--dim); }
"""

SHELL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body><header><a href="/">claude-osint</a><span>skills &amp; docs preview</span></header>
<main>{body}</main>
<script>
let rev = null;
async function poll() {{
  try {{
    const t = await (await fetch('/__rev', {{cache: 'no-store'}})).text();
    if (rev && t !== rev) location.reload();
    rev = t;
  }} catch (e) {{ /* server restarting */ }}
}}
setInterval(poll, 1000);
poll();
</script></body></html>"""


def parse_frontmatter(text: str) -> dict:
    match = FRONTMATTER.match(text)
    if not match:
        return {}
    return {key: value.strip().strip("'\"") for key, value in FIELD.findall(match.group(1))}


def skills() -> list[dict]:
    found = []
    for root in SKILL_DIRS:
        base = ROOT / root
        if not base.is_dir():
            continue
        for directory in sorted(base.iterdir()):
            skill_file = directory / "SKILL.md"
            if not skill_file.is_file():
                continue
            meta = parse_frontmatter(skill_file.read_text(encoding="utf-8"))
            found.append({
                "group": root,
                "name": meta.get("name", directory.name),
                "description": meta.get("description", ""),
                "path": skill_file.relative_to(ROOT).as_posix(),
            })
    return found


def doc_files() -> list[Path]:
    files = [ROOT / name for name in DOC_FILES if (ROOT / name).is_file()]
    for name in DOC_DIRS:
        base = ROOT / name
        if base.is_dir():
            files += sorted(base.rglob("*.md"))
    return files


def render_markdown(rel: str) -> str:
    path = (ROOT / rel).resolve()
    if not path.is_file() or ROOT not in path.parents or path.suffix.lower() != ".md":
        raise FileNotFoundError(rel)
    text = FRONTMATTER.sub("", path.read_text(encoding="utf-8"))  # metadata, not page content
    body = markdown.markdown(text, extensions=["fenced_code", "tables", "sane_lists"])

    def to_preview(match: re.Match) -> str:
        target = (path.parent / unquote(match.group(1))).resolve()
        try:
            repo_rel = target.relative_to(ROOT).as_posix()
        except ValueError:
            return match.group(0)
        return f'href="/md/{repo_rel}{match.group(2)}"'

    return MD_HREF.sub(to_preview, body)


def index_body() -> str:
    docs = "".join(
        f'<li><a href="/md/{f.relative_to(ROOT).as_posix()}">{html.escape(f.relative_to(ROOT).as_posix())}</a></li>'
        for f in doc_files()
    )
    groups = [
        (".claude/skills", "Law &amp; litigation skill pack"),
        ("skills", "OSINT skill pack"),
    ]
    sections = []
    for root, label in groups:
        entries = [s for s in skills() if s["group"] == root]
        rows = "".join(
            f'<li data-name="{html.escape(s["name"].lower())}">'
            f'<a href="/md/{s["path"]}">{html.escape(s["name"])}</a>'
            f'<p>{html.escape(s["description"])}</p></li>'
            for s in entries
        )
        sections.append(f"<h2>{label} <small>{len(entries)} skills</small></h2><ul class='skills'>{rows}</ul>")
    return (
        "<h1>Skills &amp; docs</h1>"
        "<p>Every skill and document in this repository, rendered straight from the working tree.</p>"
        '<input id="q" type="search" placeholder="Filter skills by name or description" autocomplete="off">'
        "<h2>Documentation <small>%d files</small></h2><ul class='docs'>%s</ul>%s"
        "<script>\n"
        "const q = document.getElementById('q');\n"
        "q.addEventListener('input', () => {\n"
        "  const norm = s => s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();\n"
        "  const v = norm(q.value);\n"
        "  document.querySelectorAll('ul.skills li').forEach(li => {\n"
        "    li.style.display = !v || norm(li.textContent).includes(v) ? '' : 'none';\n"
        "  });\n"
        "});\n"
        "</script>"
    ) % (len(doc_files()), docs, "".join(sections))


def page(title: str, body: str) -> bytes:
    return SHELL.format(title=html.escape(title), css=CSS, body=body).encode("utf-8")


def revision() -> str:
    newest, count = 0, 0
    for path in ROOT.rglob("*.md"):
        if ".git/" in path.as_posix():
            continue
        try:
            newest = max(newest, path.stat().st_mtime_ns)
        except OSError:
            continue
        count += 1
    return f"{count}-{newest}"


class Handler(BaseHTTPRequestHandler):
    server_version = "base44-preview"

    def send(self, status: int, body: bytes, ctype: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        try:
            if route in ("/", "/index.html"):
                self.send(200, page("Skills & docs preview", index_body()))
            elif route == "/__rev":
                self.send(200, revision().encode(), "text/plain; charset=utf-8")
            elif route.startswith("/md/"):
                rel = unquote(route[len("/md/"):])
                body = render_markdown(rel)
                self.send(200, page(rel, f'<article class="md">{body}</article>'))
            elif route.startswith("/assets/"):
                asset = (ROOT / unquote(route.lstrip("/"))).resolve()
                if not asset.is_file() or ROOT not in asset.parents:
                    self.send(404, b"not found", "text/plain; charset=utf-8")
                else:
                    ctype = mimetypes.guess_type(str(asset))[0] or "application/octet-stream"
                    self.send(200, asset.read_bytes(), ctype)
            else:
                self.send(404, b"not found", "text/plain; charset=utf-8")
        except FileNotFoundError:
            self.send(404, b"not found", "text/plain; charset=utf-8")
        except Exception as exc:  # keep the preview up, report the failure in the body
            self.send(500, f"preview error: {exc}".encode(), "text/plain; charset=utf-8")

    def log_message(self, fmt: str, *args) -> None:
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


if __name__ == "__main__":
    print(f"preview server on http://0.0.0.0:{PORT} (rendering {ROOT})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
