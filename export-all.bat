@echo off
cd /d "%~dp0"
rem keep the child process free of any injected PYTHONPATH shims
set PYTHONPATH=
rem 微信数据目录：留空则使用程序自动探测；需要手动指定时先 set WX_DB=D:\WeChatData
set "DBARG="
if not "%WX_DB%"=="" set DBARG=--db-dir "%WX_DB%"
echo Data dir: "%WX_DB%"  (empty means auto-detect)
echo Running: cli.py --all %DBARG% %*
echo.
".venv\Scripts\python.exe" cli.py --all %DBARG% %*
echo.
pause
