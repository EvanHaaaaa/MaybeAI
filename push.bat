@echo off
setlocal

set MSG=%~1
if "%MSG%"=="" set MSG=update: sync latest changes

echo [Git] Staging files...
git add .

echo [Git] Committing: "%MSG%"...
git commit -m "%MSG%"

echo [Git] Pushing to GitHub (origin main)...
git push origin main

echo [Git] Push complete!
pause
