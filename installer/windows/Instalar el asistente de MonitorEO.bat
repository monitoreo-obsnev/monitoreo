@echo off
rem Instalador del asistente de MonitorEO para Windows: se abre con doble clic (ver la pagina Asistente de la wiki).
rem
rem Instala en %USERPROFILE%\MonitorEO\entorno, sin permisos de administrador, el entorno de Python de MonitorEO
rem (Python, Earth Engine, GDAL y el paquete monitoreo, del environment.yml del repositorio) con micromamba, que deja
rem en %USERPROFILE%\MonitorEO\micromamba. Pone en el Escritorio el acceso "Asistente de MonitorEO", que lo abre, y
rem lo abre. Si el entorno ya existe, solo crea el acceso y abre el asistente; para instalarlo de nuevo, borra la
rem carpeta entorno. Sin acentos: cmd lee este fichero con la pagina de codigos de la consola.
setlocal
title Instalador del asistente de MonitorEO
set "REPO=https://raw.githubusercontent.com/monitoreo-obsnev/monitoreo/main"
set "DIR=%USERPROFILE%\MonitorEO"
set "ENV=%DIR%\entorno"
set "MAMBA_DIR=%DIR%\micromamba"
set "MAMBA=%MAMBA_DIR%\micromamba.exe"
set "PYTHONNOUSERSITE=1"

echo Instalador del asistente de MonitorEO
echo =====================================
echo.
echo Instala en %ENV%, sin permisos de administrador, lo que necesita el asistente:
echo Python, Google Earth Engine, GDAL y MonitorEO (unos 0,2 GB de descarga y 1 GB en disco). Despues, al abrirlo
echo por primera vez, el asistente descarga su modelo de lenguaje y su motor (unos 7 GB). Las dos descargas son solo
echo la primera vez.
echo.

if exist "%ENV%\python.exe" if exist "%ENV%\Scripts\monitoreo.exe" (
  echo El entorno ya esta instalado en %ENV%.
  goto :launcher
)
if not exist "%MAMBA_DIR%" mkdir "%MAMBA_DIR%"
echo 1/3 Descargando micromamba (el instalador de paquetes de conda-forge)...
set "URL=https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-win-64"
curl -fL --progress-bar -o "%MAMBA%.part" "%URL%" || goto :fail
curl -fsL -o "%MAMBA%.sha256" "%URL%.sha256" || goto :fail
powershell -NoProfile -Command "if ((Get-FileHash -Algorithm SHA256 -LiteralPath ($env:MAMBA + '.part')).Hash -ne (Get-Content -Raw -LiteralPath ($env:MAMBA + '.sha256')).Trim()) { exit 1 }" || goto :damaged
move /y "%MAMBA%.part" "%MAMBA%" >nul || goto :fail

echo 2/3 Descargando la lista de paquetes de MonitorEO...
curl -fsL -o "%DIR%\environment.yml" "%REPO%/environment.yml" || goto :fail

echo 3/3 Instalando Python, Earth Engine, GDAL y MonitorEO (unos minutos)...
if exist "%ENV%" rmdir /s /q "%ENV%"
set "MAMBA_ROOT_PREFIX=%MAMBA_DIR%"
"%MAMBA%" create -y -p "%ENV%" -f "%DIR%\environment.yml" || goto :fail
"%MAMBA%" clean -y --all >nul 2>&1
if not exist "%ENV%\Scripts\monitoreo.exe" goto :fail

:launcher
> "%DIR%\Asistente de MonitorEO.bat" (
  echo @echo off
  echo rem Abre el asistente de MonitorEO, creado por su instalador. Para cerrarlo, cierra esta ventana.
  echo title Asistente de MonitorEO
  echo echo El asistente de MonitorEO se abre en el navegador. Para cerrarlo, cierra esta ventana.
  echo set PYTHONNOUSERSITE=1
  echo "%ENV%\python.exe" -m monitoreo.cli assistant
)
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Asistente de MonitorEO.lnk')); $s.TargetPath = Join-Path $env:DIR 'Asistente de MonitorEO.bat'; $s.WorkingDirectory = $env:DIR; $s.IconLocation = (Join-Path $env:ENV 'python.exe') + ',0'; $s.Save()"

echo.
echo Listo. Para abrir el asistente otra vez: doble clic en "Asistente de MonitorEO" del Escritorio.
echo Ahora se abre en el navegador. Para cerrarlo, cierra esta ventana.
echo.
"%ENV%\python.exe" -m monitoreo.cli assistant
exit /b

:damaged
echo.
echo ERROR: la descarga de micromamba esta danada.
:fail
echo.
echo ERROR: la instalacion no ha terminado. Comprueba la conexion a internet y vuelve a abrir el instalador.
echo Si sigue fallando, mira la pagina Problemas frecuentes de la wiki de MonitorEO.
pause
exit /b 1
