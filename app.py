"""Atamation YouTube Downloader: Flask uygulaması."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

from flask import Flask, Response, jsonify, render_template, request

from services.export_jobs import ExportJobRunner
from services.job_store import JobStore
from services.youtube_service import MediaServiceError, YouTubeService


def resource_root() -> Path:
    """Geliştirme veya PyInstaller paket kökünü döndürür."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def create_app() -> Flask:
    """Şablon yolu paketlenmiş .exe ile uyumlu Flask uygulamasını üretir."""
    root = resource_root()
    application = Flask(
        __name__,
        template_folder=str(root / "templates"),
        static_folder=str(root / "static"),
        static_url_path="/static",
    )
    application.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    return application


app = create_app()
youtube_service = YouTubeService()
job_store = JobStore()
export_jobs = ExportJobRunner(youtube_service, job_store)


@app.get("/")
def index():
    """Ana düzenleme arayüzünü sunar."""
    return render_template("index.html")


@app.post("/api/analyze")
def analyze():
    """YouTube URL'sinden meta veri ve kalite listesini çıkarır."""
    payload = request.get_json(silent=True) or {}
    url = payload.get("url", "")

    try:
        metadata = youtube_service.extract_metadata(url)
        return jsonify(metadata)
    except MediaServiceError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:  # noqa: BLE001
        return jsonify({"ok": False, "error": "An unexpected analysis error occurred."}), 500


@app.post("/api/jobs")
def create_job():
    """Kesim işini arka planda başlatır ve iş kimliğini döndürür."""
    payload = request.get_json(silent=True) or {}
    try:
        job_payload = _parse_export_payload(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    try:
        youtube_service.validate_url(job_payload["url"])
        youtube_service.ensure_ffmpeg()
    except MediaServiceError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    job_id = export_jobs.start(job_payload)
    return jsonify({"ok": True, "id": job_id, "status": "queued", "percent": 0})


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str):
    """İşin yüzde ve faz bilgisini döndürür."""
    job = job_store.read(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Job not found."}), 404
    return jsonify(job_store.public_view(job))


@app.get("/api/jobs/<job_id>/file")
def get_job_file(job_id: str):
    """Hazır klibi tarayıcıya akıtır ve geçici dosyaları siler."""
    job = job_store.read(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Job not found."}), 404
    if job.get("status") == "error":
        return jsonify({"ok": False, "error": job.get("error") or "Export failed."}), 400
    if job.get("status") != "ready" or not job.get("file_path"):
        return jsonify({"ok": False, "error": "File is not ready yet."}), 409

    file_path = job["file_path"]
    download_name = job.get("download_name") or "clip"
    mime = job.get("mime") or "application/octet-stream"
    job_dir = str(job_store.job_dir(job_id))

    def generate():
        """Dosyayı parçalar halinde akıtır; bittikten sonra iş dizinini siler."""
        try:
            with open(file_path, "rb") as handle:
                while True:
                    chunk = handle.read(256 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)

    ascii_name = download_name.encode("ascii", "ignore").decode() or "clip"
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(download_name)}"
        ),
        "Cache-Control": "no-store",
    }
    return Response(generate(), mimetype=mime, headers=headers)


@app.post("/api/jobs/<job_id>/save")
def save_job_file(job_id: str):
    """Hazır klibi kullanıcının seçtiği klasöre kopyalar."""
    job = job_store.read(job_id)
    if not job:
        return jsonify({"ok": False, "error": "İş bulunamadı."}), 404
    if job.get("status") == "error":
        return jsonify({"ok": False, "error": job.get("error") or "Dışa aktarma başarısız."}), 400
    if job.get("status") != "ready" or not job.get("file_path"):
        return jsonify({"ok": False, "error": "Dosya henüz hazır değil."}), 409

    payload = request.get_json(silent=True) or {}
    directory = str(payload.get("directory") or "").strip()
    if not directory:
        return jsonify({"ok": False, "error": "Kayıt klasörü seçilmedi."}), 400

    dest_dir = Path(directory).expanduser()
    try:
        dest_dir = dest_dir.resolve()
    except OSError:
        return jsonify({"ok": False, "error": "Geçersiz klasör yolu."}), 400

    if not dest_dir.is_dir():
        return jsonify({"ok": False, "error": f"Klasör bulunamadı: {dest_dir}"}), 400

    source = Path(str(job["file_path"]))
    if not source.is_file():
        return jsonify({"ok": False, "error": "Geçici çıktı dosyası kayboldu."}), 500

    download_name = job.get("download_name") or source.name
    dest = _unique_dest_path(dest_dir, download_name)
    try:
        shutil.copy2(source, dest)
    except OSError as exc:
        return jsonify({"ok": False, "error": f"Dosya kaydedilemedi: {exc}"}), 500

    shutil.rmtree(str(job_store.job_dir(job_id)), ignore_errors=True)

    return jsonify(
        {
            "ok": True,
            "path": str(dest),
            "directory": str(dest_dir),
            "filename": dest.name,
        }
    )


@app.get("/api/defaults")
def defaults():
    """Masaüstü varsayılan kayıt klasörünü döndürür."""
    return jsonify({"ok": True, "save_dir": str(_default_save_dir())})


@app.get("/api/health")
def health():
    """Uygulama ve FFmpeg durumunu döndürür."""
    ffmpeg_ok = bool(shutil.which("ffmpeg"))
    return jsonify({"ok": True, "ffmpeg": ffmpeg_ok})


def _default_save_dir() -> Path:
    """Kullanıcı Masaüstü klasörünü döndürür; yoksa home kullanır."""
    home = Path.home()
    candidates = [
        home / "Desktop",
        home / "OneDrive" / "Desktop",
        Path(os.environ.get("USERPROFILE", str(home))) / "Desktop",
    ]
    for path in candidates:
        if path.is_dir():
            return path
    return home


def _unique_dest_path(directory: Path, filename: str) -> Path:
    """Aynı isimde dosya varsa (1), (2) soneki ekler."""
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    index = 1
    while True:
        alt = directory / f"{stem} ({index}){suffix}"
        if not alt.exists():
            return alt
        index += 1


def _parse_export_payload(payload: dict) -> dict:
    """İstemci gövdesinden kesim parametrelerini doğrular."""
    try:
        duration_raw = payload.get("duration")
        if duration_raw in (None, "", "null"):
            duration = None
            start = 0.0
            end = 0.0
        else:
            duration = float(duration_raw)
            start = float(payload.get("start", 0))
            end = float(payload.get("end", 0))
        quality = payload.get("quality")
        quality_value = int(quality) if quality not in (None, "", "best") else None
    except (TypeError, ValueError) as exc:
        raise ValueError("Time or quality values are invalid.") from exc

    url = (payload.get("url") or "").strip()
    media_type = (payload.get("media_type") or "mp4").lower().strip()
    if not url:
        raise ValueError("Please paste a valid media link.")
    return {
        "url": url,
        "start": start,
        "end": end,
        "duration": duration,
        "media_type": media_type,
        "quality": quality_value,
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
