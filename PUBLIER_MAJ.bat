@echo off
rem ============================================================
rem  Publie une MISE A JOUR de Montage Studio (quelques Mo) sur GitHub.
rem  Toutes les apps installees (toi + tes potes) la recoivent a leur prochain lancement.
rem ============================================================
chcp 65001 >nul
setlocal EnableDelayedExpansion
pushd "%~dp0"
set PYTHONUTF8=1
set "VPY=.venv\Scripts\python.exe"
if not exist "%VPY%" ( echo Lance d'abord BUILD_EXE.bat & pause & exit /b )
if not exist "update_repo.txt" ( echo Lance d'abord BUILD_EXE.bat ^(il configure le depot GitHub^) & pause & exit /b )
if not exist "licence_privee\cle_privee.pem" ( echo Cle privee introuvable dans licence_privee\ & pause & exit /b )

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

"%VPY%" -c "import common;print('Version actuelle :', common.APP_VERSION)"
set /p VER="Nouvelle version (ex 1.0.1) : "
set /p NOTES="Ce qui change (une phrase) : "
"%VPY%" publish.py %VER% "%NOTES%"
if errorlevel 1 ( echo [ERREUR] publication & pause & exit /b )
echo.
echo Pense a garder ce dossier a jour : la prochaine version partira de ce code.
pause
