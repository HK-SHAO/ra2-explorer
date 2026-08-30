@echo off
setlocal
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\privacy_scan.py --mode staged
) else (
  py -3 scripts\privacy_scan.py --mode staged
)
exit /b %errorlevel%
