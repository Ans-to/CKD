"""Tiny read-only file server used to hand rendered videos to a browser.

    python tools/serve.py --dir . --port 8000

* binds 0.0.0.0 so a sandbox/Colab proxy can reach it
* supports HTTP Range requests (so video seeking works)
* serves `.mp4` / `.zip` as attachments, everything else inline
* shows a small index of the directory

It is deliberately limited to GET/HEAD and to the directory you pass in.
"""
from __future__ import annotations

import argparse
import html
import mimetypes
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ATTACH = {".mp4", ".zip", ".srt", ".vtt", ".ass"}

INDEX = """<!doctype html><meta charset="utf-8">
<title>files</title>
<style>body{{font:16px system-ui;background:#12101a;color:#e9e6f4;padding:2rem}}
a{{color:#8fd3ff;text-decoration:none}}li{{margin:.4rem 0}}small{{color:#9a94ad}}</style>
<h2>{title}</h2><ul>{items}</ul>"""


class Handler(BaseHTTPRequestHandler):
    root: Path = Path(".")
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    def _resolve(self) -> Path | None:
        rel = unquote(urlparse(self.path).path).lstrip("/")
        target = (self.root / rel).resolve()
        if not str(target).startswith(str(self.root.resolve())):
            return None
        return target

    def _index(self, folder: Path) -> bytes:
        items = []
        for child in sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            if child.name.startswith("."):
                continue
            href = "/" + child.relative_to(self.root).as_posix() + ("/" if child.is_dir() else "")
            size = "" if child.is_dir() else f" <small>{child.stat().st_size / 1e6:.1f} MB</small>"
            items.append(f'<li><a href="{html.escape(href)}">{html.escape(child.name)}</a>{size}</li>')
        title = "/" + folder.relative_to(self.root).as_posix() if folder != self.root else "/"
        return (INDEX.format(title=html.escape(title), items="".join(items))).encode()

    def do_HEAD(self):
        self._send(head_only=True)

    def do_GET(self):
        self._send(head_only=False)

    def _send(self, *, head_only: bool):
        target = self._resolve()
        if target is None or not target.exists():
            self.send_error(404)
            return
        if target.is_dir():
            body = self._index(target)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head_only:
                self.wfile.write(body)
            return

        size = target.stat().st_size
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        partial = False
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
            if m:
                a, b = m.group(1), m.group(2)
                if a:
                    start = int(a)
                    end = int(b) if b else size - 1
                elif b:
                    start = max(0, size - int(b))
                end = min(end, size - 1)
                if start > end:
                    self.send_error(416)
                    return
                partial = True

        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if target.suffix.lower() in ATTACH:
            self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
        self.end_headers()
        if head_only:
            return
        with target.open("rb") as fh:
            fh.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = fh.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=".")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    args = ap.parse_args(argv)
    Handler.root = Path(args.dir).resolve()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"serving {Handler.root} on http://0.0.0.0:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
