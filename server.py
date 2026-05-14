import os
import re
import threading
import uuid
import time
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template, after_this_request
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

jobs = {}

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)

def cleanup_old_files():
    """Elimina archivos de más de 10 minutos"""
    while True:
        time.sleep(300)  # cada 5 minutos
        now = time.time()
        for f in DOWNLOAD_DIR.iterdir():
            try:
                if now - f.stat().st_mtime > 600:  # 10 minutos
                    f.unlink()
            except:
                pass

# Hilo de limpieza automática
threading.Thread(target=cleanup_old_files, daemon=True).start()

def progress_hook(d, job_id):
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
        downloaded = d.get("downloaded_bytes", 0)
        percent = int((downloaded / total) * 100) if total else 0
        jobs[job_id] = {
            "status": "downloading",
            "percent": percent,
            "speed": d.get("_speed_str", "-"),
            "eta": d.get("_eta_str", "-"),
            "filename": d.get("filename", ""),
        }
    elif d["status"] == "finished":
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["percent"] = 99

def do_download(job_id, url, fmt, quality):
    try:
        out_template = str(DOWNLOAD_DIR / "%(title)s.%(ext)s")

        if fmt == "mp3":
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": out_template,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "progress_hooks": [lambda d: progress_hook(d, job_id)],
                "quiet": True,
            }
        else:
            if quality == "max":
                fmt_str = "bestvideo+bestaudio/best"
            else:
                fmt_str = "bestvideo[height<={}]+bestaudio/best[height<={}]".format(quality, quality)

            ydl_opts = {
                "format": fmt_str,
                "outtmpl": out_template,
                "merge_output_format": "mp4",
                "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
                "postprocessor_args": {
                    "ffmpeg": ["-vcodec", "libx264", "-acodec", "aac", "-crf", "23", "-preset", "fast"]
                },
                "progress_hooks": [lambda d: progress_hook(d, job_id)],
                "quiet": True,
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = sanitize_filename(info.get("title", "video"))

            downloaded_file = None
            for f in DOWNLOAD_DIR.iterdir():
                if f.suffix.lstrip(".") in ["mp4", "mp3", "webm", "mkv"] and title[:20] in f.stem:
                    downloaded_file = f
                    break

            if not downloaded_file:
                files = sorted(DOWNLOAD_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
                downloaded_file = files[0] if files else None

            if downloaded_file:
                jobs[job_id] = {
                    "status": "done",
                    "percent": 100,
                    "filename": downloaded_file.name,
                    "title": info.get("title", "video"),
                    "duration": info.get("duration_string", ""),
                    "thumbnail": info.get("thumbnail", ""),
                }
            else:
                jobs[job_id] = {"status": "error", "message": "No se encontro el archivo descargado."}

    except Exception as e:
        jobs[job_id] = {"status": "error", "message": str(e)}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/info", methods=["POST"])
def get_info():
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL requerida"}), 400
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        return jsonify({
            "title": info.get("title"),
            "duration": info.get("duration_string"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "view_count": info.get("view_count"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/download", methods=["POST"])
def start_download():
    data = request.json
    url = data.get("url", "").strip()
    fmt = data.get("format", "mp4")
    quality = data.get("quality", "360")

    if not url:
        return jsonify({"error": "URL requerida"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "starting", "percent": 0}

    t = threading.Thread(target=do_download, args=(job_id, url, fmt, quality), daemon=True)
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/progress/<job_id>")
def get_progress(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job no encontrado"}), 404
    return jsonify(job)


@app.route("/file/<filename>")
def serve_file(filename):
    path = DOWNLOAD_DIR / filename
    if not path.exists():
        return jsonify({"error": "Archivo no encontrado"}), 404

    # Eliminar el archivo después de enviarlo al usuario
    @after_this_request
    def delete_file(response):
        def remove():
            time.sleep(5)
            try:
                path.unlink()
                # Limpiar el job también
                for jid, job in list(jobs.items()):
                    if job.get("filename") == filename:
                        del jobs[jid]
                        break
            except:
                pass
        threading.Thread(target=remove, daemon=True).start()
        return response

    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n UaykiDescargas corriendo en http://localhost:{port}\n")
    app.run(debug=False, host="0.0.0.0", port=port)
