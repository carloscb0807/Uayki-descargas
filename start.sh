#!/bin/bash
# =============================================
#  UaykiDownload — Instalador y lanzador
# =============================================

echo ""
echo "  🎬  UaykiDownload Setup"
echo "  ================================"

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "  ❌  Python 3 no encontrado. Instálalo desde https://python.org"
    exit 1
fi

echo "  ✅  Python encontrado: $(python3 --version)"

# Verificar ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo ""
    echo "  ⚠️   ffmpeg no encontrado. Es necesario para MP3 y algunos MP4."
    echo "  Instálalo con:"
    echo "    macOS:   brew install ffmpeg"
    echo "    Ubuntu:  sudo apt install ffmpeg"
    echo "    Windows: https://ffmpeg.org/download.html"
    echo ""
fi

# Instalar dependencias
echo ""
echo "  📦  Instalando dependencias Python..."
pip3 install -r requirements.txt -q

echo ""
echo "  🚀  Iniciando servidor en http://localhost:5000"
echo "  (Presiona Ctrl+C para detener)"
echo ""

python3 server.py
