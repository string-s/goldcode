#!/bin/zsh

set -u

BOT_DIR="${0:A:h}"
PY_BIN="$(command -v python3 2>/dev/null || true)"

if [[ -z "$PY_BIN" && -x '/opt/homebrew/bin/python3' ]]; then
    PY_BIN='/opt/homebrew/bin/python3'
fi
if [[ -z "$PY_BIN" && -x '/usr/local/bin/python3' ]]; then
    PY_BIN='/usr/local/bin/python3'
fi
if [[ -z "$PY_BIN" && -x '/usr/bin/python3' ]]; then
    PY_BIN='/usr/bin/python3'
fi

clear
print '========================================'
print '  疯狂 Geek 兔 · 参赛 BOT 开发包（Python）'
print '========================================'
print '连接与分桌链路已提供；战斗动作需要你修改 strategy.py。'
print '关闭本窗口即可让 BOT 下线。'
print ''

if [[ -z "$PY_BIN" ]]; then
    print -u2 '未检测到 Python 3.9+。请先安装：https://www.python.org/downloads/'
    read '?按回车关闭...'
    exit 1
fi

cd "$BOT_DIR" || exit 1

VENV_PY="$BOT_DIR/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
    print '首次运行，正在创建虚拟环境...'
    "$PY_BIN" -m venv .venv || {
        print -u2 '虚拟环境创建失败，请检查 Python 安装后重试。'
        read '?按回车关闭...'
        exit 1
    }
fi

if ! "$VENV_PY" -c 'import websockets' >/dev/null 2>&1; then
    print '正在自动安装 WebSocket 依赖...'
    "$VENV_PY" -m pip install --disable-pip-version-check -r requirements.txt || {
        print -u2 '依赖安装失败，请检查网络后重试。'
        read '?按回车关闭...'
        exit 1
    }
fi

read -s '?请输入 test:数字工号（推荐）或正式 AccessKey（不会显示或保存）：' CRAZY_CRASH_ACCESS_KEY
print ''
if [[ -z "$CRAZY_CRASH_ACCESS_KEY" ]]; then
    print -u2 'test:数字工号或 AccessKey 不能为空。'
    read '?按回车关闭...'
    exit 1
fi
export CRAZY_CRASH_ACCESS_KEY

print '正在连接比赛服务...'
"$VENV_PY" bot.py
BOT_STATUS=$?
unset CRAZY_CRASH_ACCESS_KEY

if (( BOT_STATUS == 0 )); then
    print '\nBOT 已下线。'
else
    print -u2 "\nBOT 已退出，状态码：$BOT_STATUS"
fi
read '?按回车关闭...'
exit "$BOT_STATUS"
