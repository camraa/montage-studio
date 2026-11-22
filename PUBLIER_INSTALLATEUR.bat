@echo off
rem ============================================================
rem  Met l'INSTALLATEUR complet en ligne (lien de telechargement pour tes clients).
rem  A relancer apres chaque BUILD_EXE.bat. Le lien ne change jamais.
rem ============================================================
chcp 65001 >nul
setlocal EnableDelayedExpansion
pushd "%~dp0"
set PYTHONUTF8=1
set "VPY=.venv\Scripts\python.exe"
if not exist "%VPY%" ( echo Lance d'abord BUILD_EXE.bat & pause & exit /b )
if not exist "update_repo.txt" ( echo Lance d'abord BUILD_EXE.bat ^(il configure le depot GitHub^) & pause & exit /b )

rem ---- outil GitHub (gh)
set "PATH=%ProgramFiles%\GitHub CLI;%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
where gh >nul 2>nul
if errorlevel 1 (
  echo [INSTALL] Outil GitHub ^(gh^)...
  winget install -e --id GitHub.cli --accept-package-agreements --accept-source-agreements
  set "PATH=%ProgramFiles%\GitHub CLI;!PATH!"
)
gh auth status >nul 2>nul
if errorlevel 1 (
  echo.
  echo Connexion a ton compte GitHub ^(une seule fois, ca ouvre le navigateur^) :
  gh auth login --web --git-protocol https
)

if not exist "dist\MontageStudio_Setup.exe" ( echo Lance d'abord BUILD_EXE.bat & pause & exit /b )
"%VPY%" publish.py --installateur
if errorlevel 1 ( echo [ERREUR] publication & pause & exit /b )
pause
