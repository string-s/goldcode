"""零依赖的本地回放服务：提供 replay.html，并代理同版本的 CDN 素材。"""

import os
import posixpath
import re
import shutil
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

DEFAULT_PORT = 9998
CDN_ROOT = "https://dev.g.alicdn.com/pengtianshun.pts/crazy-crash/0.0.1"
HTML_FILE = Path(__file__).resolve().parent / "replay.html"
FORWARDED_HEADERS = [
    "accept-ranges",
    "cache-control",
    "content-length",
    "content-type",
    "etag",
    "last-modified",
]
ASSET_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def cdn_asset_url(request_url):
    parts = urlsplit(request_url)
    # 先规范化 ".."，与浏览器的 URL 解析保持一致，避免穿越到 /build/ 之外。
    pathname = posixpath.normpath(parts.path) if parts.path else ""
    if not pathname.startswith("/build/"):
        return None
    asset_name = unquote(pathname[len("/build/"):])
    if not ASSET_NAME_PATTERN.fullmatch(asset_name):
        return None
    return f"{CDN_ROOT}/{quote(asset_name, safe='')}"


class ReplayHandler(BaseHTTPRequestHandler):
    server_version = "crazy-crash-local-replay/1.0"

    def do_GET(self):
        self.handle_read()

    def do_HEAD(self):
        self.handle_read()

    def do_POST(self):
        self.send_text(405, "只支持 GET 和 HEAD 请求")

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST
    do_OPTIONS = do_POST

    def log_message(self, *args):
        pass  # 本地回放服务不打印访问日志

    def handle_read(self):
        asset_url = cdn_asset_url(self.path)
        if asset_url:
            self.proxy_asset(asset_url)
            return

        url = urlsplit(self.path)
        if url.path in ("/", "/game", "/game/", "/replay.html"):
            self.serve_html(url)
            return

        self.send_text(404, "未找到")

    def send_text(self, status_code, body):
        payload = body.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def serve_html(self, url):
        query = parse_qsl(url.query, keep_blank_values=True)
        if url.path != "/game" or dict(query).get("mode") != "replay":
            pairs = [(key, value) for key, value in query if key != "mode"]
            pairs.append(("mode", "replay"))
            self.send_response(302)
            self.send_header("Location", "/game?" + urlencode(pairs))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        try:
            html = HTML_FILE.read_bytes()
        except OSError as error:
            self.send_text(500, f"无法读取 replay.html：{error}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(html)

    def proxy_asset(self, target_url):
        request = urllib.request.Request(
            target_url, method=self.command,
            headers={"User-Agent": "crazy-crash-local-replay/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=15) as upstream:
                self.forward(upstream, upstream.status)
        except urllib.error.HTTPError as error:
            with error:
                self.forward(error, error.code)
        except Exception as error:
            self.send_text(502, f"CDN 素材加载失败：{error}")

    def forward(self, upstream, status_code):
        self.send_response(status_code)
        for name in FORWARDED_HEADERS:
            value = upstream.headers.get(name)
            if value is not None:
                self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            shutil.copyfileobj(upstream, self.wfile)


def create_server(port=DEFAULT_PORT, host="127.0.0.1"):
    return ThreadingHTTPServer((host, port), ReplayHandler)


def main():
    raw_port = os.environ.get("REPLAY_PORT") or str(DEFAULT_PORT)
    try:
        port = int(raw_port)
    except ValueError:
        port = -1
    if port < 1 or port > 65535:
        print("REPLAY_PORT 必须是 1 到 65535 之间的整数", file=sys.stderr)
        return 1

    server = create_server(port)
    print(f"本地回放页：http://127.0.0.1:{port}/game?mode=replay")
    print("按 Ctrl+C 停止服务")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
