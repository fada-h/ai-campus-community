@echo off
chcp 936 >nul
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ============================================
echo   AI校园社区  一键启动
echo   后端 http://127.0.0.1:8000   前端 http://127.0.0.1:5173
echo ============================================
echo.

if not exist "backend\.venv\Scripts\python.exe" goto NOT_READY
if not exist "frontend\node_modules" goto NOT_READY

powershell -NoProfile -Command "if(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue){exit 1}else{exit 0}" >nul 2>nul
if errorlevel 1 (
  echo [X] 8000 端口被占了，先把占用的程序关掉再启动
  pause
  exit /b 1
)
powershell -NoProfile -Command "if(Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue){exit 1}else{exit 0}" >nul 2>nul
if errorlevel 1 (
  echo [X] 5173 端口被占了，先把占用的程序关掉再启动
  pause
  exit /b 1
)

echo [1/3] 起后端 ...
start "AI校园社区-后端" /D "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo [2/3] 等后端就绪 ...
set READY=0
for /l %%i in (1,1,45) do (
  if "!READY!"=="0" (
    powershell -NoProfile -Command "try{$r=Invoke-WebRequest http://127.0.0.1:8000/api/health -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -eq 200){exit 0}}catch{}; exit 1" >nul 2>nul
    if errorlevel 1 (
      timeout /t 1 /nobreak >nul
    ) else (
      set READY=1
    )
  )
)
if "!READY!"=="0" (
  echo [X] 后端没起来，看看「AI校园社区-后端」那个窗口的报错
  pause
  exit /b 1
)
echo     后端 OK

echo [3/3] 起前端 ...
start "AI校园社区-前端" /D "%~dp0frontend" cmd /k "npm run dev"

set WEB=0
for /l %%i in (1,1,45) do (
  if "!WEB!"=="0" (
    powershell -NoProfile -Command "try{$r=Invoke-WebRequest http://127.0.0.1:5173 -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -eq 200){exit 0}}catch{}; exit 1" >nul 2>nul
    if errorlevel 1 (
      timeout /t 1 /nobreak >nul
    ) else (
      set WEB=1
    )
  )
)
if "!WEB!"=="0" (
  echo [X] 前端没起来，看看「AI校园社区-前端」那个窗口
  pause
  exit /b 1
)

start "" http://127.0.0.1:5173
echo.
echo 都起来了：
echo   前端     http://127.0.0.1:5173
echo   接口文档 http://127.0.0.1:8000/docs
echo   演示账号 linxiaoman / 123456
echo 关掉那两个黑窗口就停了。
pause
exit /b 0

:NOT_READY
echo [X] 还没装好，先双击「一键安装.cmd」
pause
exit /b 1
