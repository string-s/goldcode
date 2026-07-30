@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   疯狂 Geek 兔 · 参赛 BOT 开发包（Python）
echo ========================================
echo 连接与分桌链路已提供；战斗动作需要你修改 strategy.py。
echo 关闭本窗口即可让 BOT 下线。
echo.

set "PY_BIN="
where py >nul 2>nul && set "PY_BIN=py -3"
if not defined PY_BIN (
  where python >nul 2>nul && set "PY_BIN=python"
)
if not defined PY_BIN (
  echo 未检测到 Python 3.9+。请先安装：https://www.python.org/downloads/
  pause
  exit /b 1
)

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo 首次运行，正在创建虚拟环境...
  %PY_BIN% -m venv .venv
  if errorlevel 1 (
    echo 虚拟环境创建失败，请检查 Python 安装后重试。
    pause
    exit /b 1
  )
)

"%VENV_PY%" -c "import websockets" >nul 2>nul
if errorlevel 1 (
  echo 正在自动安装 WebSocket 依赖...
  "%VENV_PY%" -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 (
    echo 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
  )
)

for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$s=Read-Host '请输入 test:数字工号（推荐）或正式 AccessKey（不会显示或保存）' -AsSecureString; $b=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s); try {[Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)} finally {[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b)}"`) do set "CRAZY_CRASH_ACCESS_KEY=%%A"

if not defined CRAZY_CRASH_ACCESS_KEY (
  echo test:数字工号或 AccessKey 不能为空。
  pause
  exit /b 1
)

echo 正在连接比赛服务...
"%VENV_PY%" bot.py
set "BOT_STATUS=%ERRORLEVEL%"
set "CRAZY_CRASH_ACCESS_KEY="

echo.
if "%BOT_STATUS%"=="0" (
  echo BOT 已下线。
) else (
  echo BOT 已退出，状态码：%BOT_STATUS%
)
pause
exit /b %BOT_STATUS%
