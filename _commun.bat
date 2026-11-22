@echo off
rem Partie commune des 3 lanceurs : installation + montage.  Usage : _commun.bat MODE [videos...]
chcp 65001 >nul
setlocal EnableDelayedExpansion
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
pushd "%~dp0"
title Montage Fortnite - %1

echo ============================================================
echo   MONTAGE AUTO FORTNITE  -  mode %1
echo ============================================================
echo.

rem ---------------------------------------------------------------- Python
rem (le "python" du Microsoft Store est un faux raccourci : on verifie qu'il s'execute vraiment)
call :findpy
if not defined PY (
  echo [INSTALL] Python 3.12 introuvable ^(PyTorch ne supporte pas encore 3.14/3.15^) -^> installation...
  py install 3.12 >nul 2>nul
  call :findpy
)
if not defined PY (
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  call :findpy
)
if not defined PY (
  echo [ERREUR] Python 3.12 introuvable. Installe Python 3.12 depuis python.org puis relance.
  pause
  exit /b
)
echo [OK] Python : !PY!

rem ---------------------------------------------------------------- FFmpeg
set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
call :findff
if not defined FFOK (
  echo [INSTALL] FFmpeg introuvable -^> installation via winget ^(build Gyan, avec NVENC^)...
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
  call :findff
)
if not defined FFOK (
  echo [ERREUR] FFmpeg toujours introuvable. Ferme cette fenetre et relance le .bat.
  pause
  exit /b
)
ffmpeg -hide_banner -encoders 2>nul | findstr /C:"h264_nvenc" >nul
if errorlevel 1 (
  echo [ERREUR] Ton FFmpeg n'a pas h264_nvenc. Installe la build Gyan : winget install Gyan.FFmpeg
  pause
  exit /b
)
echo [OK] FFmpeg avec NVENC

rem ---------------------------------------------------------------- venv + paquets
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys;sys.exit(0 if sys.version_info[:2] in ((3,12),(3,13)) else 1)"
  if errorlevel 1 (
    echo [INSTALL] Ancien environnement avec une mauvaise version de Python -^> suppression...
    rmdir /s /q ".venv"
  )
)
if not exist ".venv\Scripts\python.exe" (
  echo [INSTALL] Creation de l'environnement Python...
  "!PY!" -m venv .venv
  if errorlevel 1 ( echo [ERREUR] venv & pause & exit /b )
)
set "VPY=.venv\Scripts\python.exe"
if not exist ".venv\installed.ok" (
  echo [INSTALL] PyTorch CUDA 12.8 ^(compatible RTX 50xx^) - ~3 Go, patience...
  "%VPY%" -m pip install --upgrade pip
  "%VPY%" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
  if errorlevel 1 ( echo [ERREUR] torch & pause & exit /b )
  echo [INSTALL] EasyOCR, OpenCV, Pillow...
  "%VPY%" -m pip install easyocr pillow numpy
  if errorlevel 1 ( echo [ERREUR] easyocr & pause & exit /b )
  rem easyocr installe OpenCV "headless" sans fenetres : on le remplace par la version complete
  "%VPY%" -m pip uninstall -y opencv-python-headless
  "%VPY%" -m pip install --force-reinstall --no-deps opencv-python
  "%VPY%" -c "import torch,cv2,easyocr;print('CUDA:',torch.cuda.is_available(),torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
  if errorlevel 1 ( echo [ERREUR] verification & pause & exit /b )
  echo ok> ".venv\installed.ok"
)

rem ---------------------------------------------------------------- musiques

rem ---------------------------------------------------------------- installation seule
if /i "%~1"=="setup" exit /b 0

rem ---------------------------------------------------------------- studio (interface)
if /i "%~1"=="studio" (
  echo.
  echo Le studio s'ouvre dans ton navigateur : http://127.0.0.1:8765
  echo Laisse cette fenetre ouverte pendant que tu montes ^(la fermer = quitter le studio^).
  echo.
  "%VPY%" studio.py
  exit /b
)

rem ---------------------------------------------------------------- montage
echo.
echo Choisis tes videos dans la fenetre qui s'ouvre (Ctrl+clic = plusieurs),
echo ou glisse directement tes videos sur le .bat.
echo.
"%VPY%" run.py %*
echo.
echo ============================================================
echo   TERMINE ! Les montages sont a cote de tes videos.
echo ============================================================
start "" explorer "%USERPROFILE%\Videos"
pause
exit /b


rem ================================================================ fonctions
:findpy
set "PY="
for %%V in (3.12 3.13) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul
    if not errorlevel 1 for /f "delims=" %%P in ('py -%%V -c "import sys;print(sys.executable)"') do set "PY=%%P"
  )
)
if defined PY exit /b
for %%D in ("%LOCALAPPDATA%\Python\pythoncore-3.12-64" "%LOCALAPPDATA%\Programs\Python\Python312" "%LOCALAPPDATA%\Python\pythoncore-3.13-64" "%LOCALAPPDATA%\Programs\Python\Python313") do (
  if not defined PY if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
)
exit /b

:findff
set "FFOK="
ffmpeg -version >nul 2>nul
if not errorlevel 1 ( set "FFOK=1" & exit /b )
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*") do (
  for /d %%B in ("%%D\ffmpeg-*") do if exist "%%B\bin\ffmpeg.exe" set "PATH=%%B\bin;!PATH!"
)
ffmpeg -version >nul 2>nul
if not errorlevel 1 set "FFOK=1"
exit /b
