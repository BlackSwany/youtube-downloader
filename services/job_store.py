"""Dosya tabanlı dışa aktarma iş durumu deposu."""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path
from typing import Any


class JobStore:
    """İş durumunu geçici dizinde JSON olarak tutar."""

    def __init__(self) -> None:
        self.root = Path(tempfile.gettempdir()) / "framecut_jobs"
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self) -> str:
        """Yeni bir iş kimliği ve dizin oluşturur."""
        job_id = uuid.uuid4().hex[:16]
        self.job_dir(job_id).mkdir(parents=True, exist_ok=True)
        self.write(
            job_id,
            {
                "id": job_id,
                "status": "queued",
                "percent": 0,
                "phase": "Queued",
                "error": None,
                "file_path": None,
                "download_name": None,
                "mime": None,
            },
        )
        return job_id

    def job_dir(self, job_id: str) -> Path:
        """İşin çalışma dizinini döndürür."""
        safe_id = self._safe_id(job_id)
        return self.root / safe_id

    def work_dir(self, job_id: str) -> Path:
        """yt-dlp / FFmpeg çıktı klasörünü döndürür."""
        path = self.job_dir(job_id) / "work"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def read(self, job_id: str) -> dict[str, Any] | None:
        """İş durumunu okur; yoksa None döner."""
        status_path = self.job_dir(job_id) / "status.json"
        if not status_path.is_file():
            return None
        try:
            return json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def write(self, job_id: str, payload: dict[str, Any]) -> None:
        """İş durumunu atomik olarak yazar."""
        directory = self.job_dir(job_id)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "status.json"
        temp = directory / "status.json.tmp"
        temp.write_text(json.dumps(payload), encoding="utf-8")
        temp.replace(target)

    def patch(self, job_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Mevcut duruma alan ekler ve kaydeder."""
        current = self.read(job_id) or {"id": job_id}
        current.update(updates)
        self.write(job_id, current)
        return current

    def public_view(self, job: dict[str, Any]) -> dict[str, Any]:
        """İstemciye güvenli iş özetini döndürür."""
        return {
            "ok": True,
            "id": job.get("id"),
            "status": job.get("status"),
            "percent": int(job.get("percent") or 0),
            "phase": job.get("phase") or "",
            "error": job.get("error"),
        }

    def _safe_id(self, job_id: str) -> str:
        """Yol kaçışına karşı iş kimliğini sadeleştirir."""
        cleaned = "".join(ch for ch in job_id if ch.isalnum())
        if not cleaned:
            raise ValueError("Invalid job id")
        return cleaned[:16]
