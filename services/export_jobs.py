"""Arka planda kesim işlerini başlatan orkestrasyon katmanı."""

from __future__ import annotations

import threading
from typing import Any

from services.job_store import JobStore
from services.youtube_service import MediaServiceError, YouTubeService


class ExportJobRunner:
    """İndirme/kesim işini ayrı bir iş parçacığında çalıştırır."""

    def __init__(self, youtube: YouTubeService, store: JobStore) -> None:
        self.youtube = youtube
        self.store = store

    def start(self, payload: dict[str, Any]) -> str:
        """Yeni işi kuyruğa alır ve iş kimliğini döndürür."""
        job_id = self.store.create()
        thread = threading.Thread(
            target=self._run,
            args=(job_id, payload),
            daemon=True,
            name=f"framecut-{job_id}",
        )
        thread.start()
        return job_id

    def _run(self, job_id: str, payload: dict[str, Any]) -> None:
        """yt-dlp + FFmpeg hattını çalıştırır ve durumu günceller."""

        def progress(percent: int, phase: str) -> None:
            self.store.patch(
                job_id,
                {
                    "status": "running",
                    "percent": max(0, min(100, int(percent))),
                    "phase": phase,
                },
            )

        try:
            self.store.patch(job_id, {"status": "running", "percent": 1, "phase": "Başlatılıyor…"})
            file_path, download_name, mime = self.youtube.download_range(
                url=payload["url"],
                start=payload["start"],
                end=payload["end"],
                media_type=payload["media_type"],
                quality=payload["quality"],
                duration=payload["duration"],
                workdir=str(self.store.work_dir(job_id)),
                progress_cb=progress,
            )
            self.store.patch(
                job_id,
                {
                    "status": "ready",
                    "percent": 100,
                    "phase": "Hazır",
                    "file_path": file_path,
                    "download_name": download_name,
                    "mime": mime,
                    "error": None,
                },
            )
        except MediaServiceError as exc:
            self.store.patch(
                job_id,
                {
                    "status": "error",
                    "phase": "Hata",
                    "error": str(exc),
                },
            )
        except Exception:  # noqa: BLE001
            self.store.patch(
                job_id,
                {
                    "status": "error",
                    "phase": "Hata",
                    "error": "İndirme sırasında beklenmeyen bir hata oluştu.",
                },
            )
