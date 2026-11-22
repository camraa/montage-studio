@echo off
rem ============================================================
rem  Fabrique MontageStudio.exe + l'installateur a donner a tes clients
rem ============================================================
chcp 65001 >nul
setlocal EnableDelayedExpansion
pushd "%~dp0"
title Build Montage Studio

echo [1/7] Environnement Python...
call "%~dp0_commun.bat" setup
if errorlevel 1 ( echo [ERREUR] installation & pause & exit /b )
set "VPY=.venv\Scripts\python.exe"
set PYTHONUTF8=1

echo [2/7] Outils de build (PyInstaller, pywebview)...
"%VPY%" -m pip install --upgrade pyinstaller pywebview >nul
if errorlevel 1 ( echo [ERREUR] pip & pause & exit /b )

echo [3/7] Depot GitHub des mises a jour automatiques...
if not exist "update_repo.txt" (
  echo.
  echo  Les mises a jour passent par un depot GitHub PUBLIC qui ne contient que les paquets de mise a jour.
  echo  Format : ton-pseudo-github/montage-studio   ^(ou juste ton pseudo : montage-studio sera ajoute^)
  set /p REPO="  Depot GitHub : "
  >"update_repo.txt" echo !REPO!
)
"%VPY%" -c "from updater import normalize_repo as n;r=n(open('update_repo.txt',encoding='utf-8').read());open('update_repo.txt','w',encoding='utf-8').write(r+'\n');open('update_cfg.py','w',encoding='utf-8').write(f'REPO = \"{r}\"\n');print('     ->',r)"
if errorlevel 1 ( echo [ERREUR] nom de depot & pause & exit /b )

echo [4/7] Modeles OCR...
if not exist "build_assets\ocr_models" mkdir "build_assets\ocr_models"
"%VPY%" -c "import easyocr;easyocr.Reader(['en','fr'],gpu=False,verbose=False,model_storage_directory=r'build_assets\ocr_models',user_network_directory=r'build_assets\ocr_models')"
if errorlevel 1 ( echo [ERREUR] modeles OCR & pause & exit /b )

echo [5/7] FFmpeg...
if not exist "build_assets\ffmpeg" mkdir "build_assets\ffmpeg"
set "FF="
for /f "delims=" %%F in ('where ffmpeg 2^>nul') do if not defined FF set "FF=%%F"
if not defined FF ( echo [ERREUR] ffmpeg introuvable : lance d'abord un des MONTAGE_*.bat & pause & exit /b )
for %%D in ("!FF!") do set "FFDIR=%%~dpD"
copy /y "!FFDIR!ffmpeg.exe" "build_assets\ffmpeg\" >nul
copy /y "!FFDIR!ffprobe.exe" "build_assets\ffmpeg\" >nul
copy /y "!FFDIR!*.dll" "build_assets\ffmpeg\" >nul 2>nul
for %%L in ("!FFDIR!..\LICENSE" "!FFDIR!..\LICENSE.txt") do if exist %%L copy /y %%L "build_assets\ffmpeg\LICENSE_FFMPEG.txt" >nul

echo [6/7] Construction de l'application (5 a 15 min, ~3 Go)...
"%VPY%" -m PyInstaller --noconfirm --clean MontageStudio.spec
if errorlevel 1 ( echo [ERREUR] PyInstaller & pause & exit /b )
copy /y CONDITIONS.txt "dist\MontageStudio\" >nul

echo [7/7] Installateur...
set "ISCC="
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do if exist %%P set "ISCC=%%~P"
if not defined ISCC (
  echo     Inno Setup absent -^> installation...
  winget install -e --id JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements >nul
  for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do if exist %%P set "ISCC=%%~P"
)
if defined ISCC (
  "!ISCC!" /Q installer.iss
  if errorlevel 1 ( echo [ATTENTION] installateur non cree, l'app reste utilisable dans dist\MontageStudio )
) else (
  echo [ATTENTION] Inno Setup indisponible : l'app est dans dist\MontageStudio ^(dossier a zipper^)
)

echo.
echo ============================================================
echo   TERMINE !
echo   Application : dist\MontageStudio\MontageStudio.exe
echo   Installateur : dist\MontageStudio_Setup.exe ^(+ fichiers .bin^)
echo   Pour le mettre en ligne ^(lien a donner a tes clients^) : PUBLIER_INSTALLATEUR.bat
echo ============================================================
start "" explorer "%~dp0dist"
pause
