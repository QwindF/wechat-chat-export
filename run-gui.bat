@echo off
cd /d "%~dp0"
rem keep the child process free of any injected PYTHONPATH shims
set PYTHONPATH=
start "" ".venv\Scripts\pythonw.exe" app.py
