@echo off
rem ============================================================
rem  Fabrique l'app (dist\MontageStudio). A relancer SEULEMENT quand une nouvelle
rem  bibliotheque arrive. Pour une simple modif du code : PUBLIER_MAJ.bat (30 s).
rem  BUILD_EXE.bat clean = reconstruction complete (si un build bizarre plante)
rem ============================================================
chcp 65001 >nul
setlocal EnableDelayedExpansion
pushd "%~dp0"
title Build Montage Studio

echo [1/6] Environnement Python...
call "%~dp0_commun.bat" setup
if errorlevel 1 ( echo [ERREUR] installation & pause & exit /b )
set "VPY=.venv\Scripts\python.exe"
set PYTHONUTF8=1

echo [2/6] Outils de build (PyInstaller, pywebview)...
"%VPY%" -m pip install --upgrade pyinstaller pywebview >nul
if errorlevel 1 ( echo [ERREUR] pip & pause & exit /b )

echo [3/6] Depot GitHub des mises a jour automatiques...
if not exist "update_repo.txt" (
  echo.
  echo  Les mises a jour passent par un depot GitHub PUBLIC qui ne contient que les paquets de mise a jour.
  echo  Format : ton-pseudo-github/montage-studio   ^(ou juste ton pseudo : montage-studio sera ajoute^)
  set /p REPO="  Depot GitHub : "
  >"update_repo.txt" echo !REPO!
)
"%VPY%" -c "from updater import normalize_repo as n;r=n(open('update_repo.txt',encoding='utf-8').read());open('update_repo.txt','w',encoding='utf-8').write(r+'\n');open('update_cfg.py','w',encoding='utf-8').write(f'REPO = \"{r}\"\n');print('     ->',r)"
if errorlevel 1 ( echo [ERREUR] nom de depot & pause & exit /b )

"%VPY%" publish.py --version-build

echo [4/6] Modeles OCR...
if not exist "build_assets\ocr_models" mkdir "build_assets\ocr_models"
if not exist "build_assets\ocr_models\latin_g2.pth" (
  "%VPY%" -c "import easyocr;easyocr.Reader(['en','fr'],gpu=False,verbose=False,model_storage_directory=r'build_assets\ocr_models',user_network_directory=r'build_assets\ocr_models')"
  if errorlevel 1 ( echo [ERREUR] modeles OCR & pause & exit /b )
) else ( echo      deja la )

echo      Modeles de transcription ^(voix^) et de detourage ^(skins^)...
if not exist "build_assets\whisper_models\small\model.bin" (
  "%VPY%" -c "from faster_whisper import download_model;download_model('small',output_dir=r'build_assets\whisper_models\small')"
  if errorlevel 1 ( echo [ATTENTION] modele de transcription non telecharge : il le sera au 1er Short )
)
if not exist "build_assets\rembg_models\isnet-general-use.onnx" (
  "%VPY%" -c "import os,urllib.request as u;p=r'build_assets\rembg_models\isnet-general-use.onnx';os.makedirs(os.path.dirname(p),exist_ok=True);u.urlretrieve('https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx',p)"
  if errorlevel 1 ( echo [ATTENTION] modele de detourage non telecharge : il le sera au 1er detourage )
)

echo [5/6] FFmpeg...
if not exist "build_assets\ffmpeg" mkdir "build_assets\ffmpeg"
set "FF="
rem ffmpeg tout juste installe par winget : pas encore dans le PATH de cette fenetre
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*") do for /d %%B in ("%%D\ffmpeg-*") do if exist "%%B\bin\ffmpeg.exe" set "PATH=%%B\bin;!PATH!"
for /f "delims=" %%F in ('where ffmpeg 2^>nul') do if not defined FF set "FF=%%F"
if not defined FF ( echo [ERREUR] ffmpeg introuvable : ferme cette fenetre et relance BUILD_EXE.bat & pause & exit /b )
for %%D in ("!FF!") do set "FFDIR=%%~dpD"
copy /y "!FFDIR!ffmpeg.exe" "build_assets\ffmpeg\" >nul
copy /y "!FFDIR!ffprobe.exe" "build_assets\ffmpeg\" >nul
copy /y "!FFDIR!*.dll" "build_assets\ffmpeg\" >nul 2>nul
for %%L in ("!FFDIR!..\LICENSE" "!FFDIR!..\LICENSE.txt") do if exist %%L copy /y %%L "build_assets\ffmpeg\LICENSE_FFMPEG.txt" >nul

set "CLEAN="
if /i "%~1"=="clean" set "CLEAN=--clean"
if defined CLEAN ( echo [6/6] Construction complete de l'application ^(5 a 15 min^)... ) else ( echo [6/6] Construction de l'application ^(rapide si deja construite une fois^)... )
"%VPY%" -m PyInstaller --noconfirm !CLEAN! MontageStudio.spec
if errorlevel 1 ( echo [ERREUR] PyInstaller & pause & exit /b )
copy /y CONDITIONS.txt "dist\MontageStudio\" >nul

echo.
echo ============================================================
echo   TERMINE !
echo   Application : dist\MontageStudio\MontageStudio.exe ^(lancable directement^)
echo   Installateur + lien pour tes clients : PUBLIER_INSTALLATEUR.bat
echo ============================================================
start "" explorer "%~dp0dist\MontageStudio"
pause
