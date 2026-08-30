@echo off
setlocal
if not exist ".venv\Scripts\ra2exp.exe" (
  echo RA2 Explorer development environment is not installed.
  exit /b 2
)
".venv\Scripts\ra2exp.exe" package --output ".outputs\RA2-Explorer-Web" --overwrite %*
exit /b %errorlevel%
