"""验证 CDN 素材代理只放行 /build/ 下的单层文件名，且回放页仍能启动。"""

import re
from pathlib import Path

from tools.replay_server import CDN_ROOT, cdn_asset_url

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

assert cdn_asset_url("/build/013787b6d91844317eb77df199481c7d.png") == \
    f"{CDN_ROOT}/013787b6d91844317eb77df199481c7d.png"
assert cdn_asset_url("/build/game.mp3?cache=1") == f"{CDN_ROOT}/game.mp3"
assert cdn_asset_url("/build/../secret.txt") is None
assert cdn_asset_url("/build/%2e%2e%2fsecret.txt") is None
assert cdn_asset_url("/build/nested/asset.png") is None
assert cdn_asset_url("/other/asset.png") is None
assert cdn_asset_url("/build/") is None

html = (PROJECT_DIR / "tools" / "replay.html").read_text(encoding="utf-8")
assert re.search(r"https://dev\.g\.alicdn\.com/pengtianshun\.pts/crazy-crash/0\.0\.1", html)
assert re.search(r"current\.pathname = '/game'", html)
assert re.search(r"searchParams\.set\('mode', 'replay'\)", html)
assert re.search(r'id="game-content"', html)
assert re.search(r"""PUBLIC_PATH_MARKER = 'i\.p="/build/"'""", html)
assert re.search(r"var GAME_PATH_MARKER", html)

print("Replay server tests passed.")
