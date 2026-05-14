import os
import re
import threading
import uuid
import time
import random
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template, after_this_request
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

jobs = {}

# User agents de navegadores reales actualizados
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

BASE_OPTS = {
    "geo_bypass": True,
    "geo_bypass_country": "PE",
    "nocheckcertificate": True,
    "user_agent": random.choice(USER_AGENTS),
    # Simular cliente Android — YouTube no pide bot check en este cliente
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "web"],
            "player_skip": ["webpage", "configs"],
        }
    },
    "http_headers": {
        "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
    "sleep_interval": 2,
    "max_sleep_interval": 5,
}

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)

def cleanup_old_files():
    while True:
        time.sleep(300)
        now = time.time()
        for f in DOWNLOAD_DIR.iterdir():
            try:
                if now - f.stat().st_mtime > 600:
                    f.unlink()
            except:
                pass

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

        base_opts = {
            **BASE_OPTS,
            "user_agent": random.choice(USER_AGENTS),  # rotar por descarga
            "progress_hooks": [lambda d: progress_hook(d, job_id)],
            "quiet": True,
        }

        if fmt == "mp3":
            ydl_opts = {
                **base_opts,
                "format": "bestaudio/best",
                "outtmpl": out_template,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }
        else:
            if quality == "max":
                fmt_str = "bestvideo+bestaudio/best"
            else:
                fmt_str = "bestvideo[height<={}]+bestaudio/best[height<={}]".format(quality, quality)

            ydl_opts = {
                **base_opts,
                "format": fmt_str,
                "outtmpl": out_template,
                "merge_output_format": "mp4",
                "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
                "postprocessor_args": {
                    "ffmpeg": ["-vcodec", "libx264", "-acodec", "aac", "-crf", "23", "-preset", "fast"]
                },
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
        error_msg = str(e)
        if "Sign in" in error_msg or "bot" in error_msg.lower():
            jobs[job_id] = {
                "status": "error",
                "message": "YouTube bloqueó la solicitud. Intenta de nuevo en unos minutos."
            }
        elif "not available in your country" in error_msg:
            jobs[job_id] = {
                "status": "error",
                "message": "Este video tiene restricción geográfica estricta."
            }
        else:
            jobs[job_id] = {"status": "error", "message": error_msg}


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
        opts = {**BASE_OPTS, "quiet": True, "skip_download": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
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

    @after_this_request
    def delete_file(response):
        def remove():
            time.sleep(5)
            try:
                path.unlink()
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
