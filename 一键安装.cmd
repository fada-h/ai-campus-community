@echo off
chcp 936 >nul
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ============================================
echo   AI校园社区  一键安装
echo   后端 FastAPI  +  前端 Vue 3 / Vite
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [X] 没检测到 python，请先装 Python 3.10+，安装时勾选 Add to PATH
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo [X] 没检测到 npm，请先装 Node.js 18+，装完重开这个窗口
  pause
  exit /b 1
)

echo [1/4] 建虚拟环境、装后端依赖
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 (
    echo [X] 虚拟环境创建失败，检查一下 Python 是否完整
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
if errorlevel 1 (
  echo     直连有点慢，换清华镜像再试一次...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple
  if errorlevel 1 (
    echo [X] 后端依赖装不上，检查网络，或手动执行 backend\requirements.txt 里的安装
    pause
    exit /b 1
  )
)

echo [2/4] 准备环境变量
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo     已生成 backend\.env（默认 SQLite，不用装 MySQL 也能跑）
)

echo [3/4] 装前端依赖
cd /d "%~dp0frontend"
if not exist "node_modules" (
  call npm install --no-audit --no-fund
  if errorlevel 1 (
    echo     换成国内镜像再试一次...
    call npm install --no-audit --no-fund --registry=https://registry.npmmirror.com
    if errorlevel 1 (
      echo [X] 前端依赖装不上，检查网络或 Node.js 版本（建议 18+）
      pause
      exit /b 1
    )
  )
)

echo [4/4] 建表 + 写演示数据
cd /d "%~dp0backend"
".venv\Scripts\python.exe" scripts\init_db.py
if errorlevel 1 (
  echo [X] 数据库初始化失败，看下上面那行报错
  pause
  exit /b 1
)

cd /d "%~dp0"
echo.
echo 装好了。双击「启动.cmd」就能跑。
pause
