@echo off
echo.
echo   UaykiDownload Setup
echo   ================================

python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo   ERROR: Python no encontrado.
    echo   Descargalo desde https://python.org
    echo   Asegurate de marcar "Add Python to PATH" al instalar.
    echo.
    pause
    exit
)

echo   Python encontrado:
python --version

echo.
echo   Instalando dependencias...
python -m pip install --upgrade pip -q
python -m pip install flask flask-cors yt-dlp -q

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo   ERROR al instalar dependencias.
    echo   Intenta correr como Administrador.
    pause
    exit
)

echo   Dependencias instaladas correctamente.
echo.
echo   Iniciando en http://localhost:5000
echo   Abre tu navegador en: http://localhost:5000
echo   Presiona Ctrl+C para detener
echo.

python server.py
pause
