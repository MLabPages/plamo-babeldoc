@echo off
rem PDF をこのファイルにドラッグ＆ドロップすると、PC 上の PLaMo で翻訳します。
chcp 65001 > nul
cd /d "%~dp0"
if "%~1"=="" (
  echo 翻訳したい PDF をこのファイルにドラッグ＆ドロップしてください。
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_server.ps1" || (pause & exit /b 1)
set PYTHONIOENCODING=utf-8
:loop
if "%~1"=="" goto done
echo.
echo 翻訳中: %~nx1
".venv\Scripts\python.exe" run_plamo.py "%~1"
shift
goto loop
:done
echo.
echo 完了しました。結果は output フォルダにあります。
start "" "%~dp0output"
pause
