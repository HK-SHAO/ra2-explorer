@echo off
setlocal
git config core.hooksPath .githooks
if errorlevel 1 exit /b %errorlevel%
echo Git privacy checks enabled for this clone.
