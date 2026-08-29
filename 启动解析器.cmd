@echo off
setlocal
cd /d "%~dp0"
set "APP=%~dp0dist\social_article_parser.exe"
if not exist "%APP%" (
  echo Parser EXE not found: "%APP%"
  echo Please rebuild it with 打包成EXE.ps1.
  pause
  exit /b 1
)
start "" "%APP%"
exit /b 0
