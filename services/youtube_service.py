"""Çok platformlu medya çıkarma ve FFmpeg destekli aralık indirme servisi."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ProgressCallback = Callable[[int, str], None]

import yt_dlp


class MediaServiceError(Exception):
    """Kullanıcıya gösterilebilir medya işleme hatası."""


class YouTubeService:
    """yt-dlp ve FFmpeg ile çok platformlu analiz / kesim işlemlerini yönetir."""

    YOUTUBE_HOSTS = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
        "www.youtu.be",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
    }
    PLATFORM_HOSTS: dict[str, set[str]] = {
        "youtube": YOUTUBE_HOSTS,
        "tiktok": {
            "tiktok.com",
            "www.tiktok.com",
            "m.tiktok.com",
            "vm.tiktok.com",
            "vt.tiktok.com",
        },
        "instagram": {
            "instagram.com",
            "www.instagram.com",
            "instagr.am",
        },
        "twitter": {
            "twitter.com",
            "www.twitter.com",
            "mobile.twitter.com",
            "x.com",
            "www.x.com",
            "mobile.x.com",
        },
        "facebook": {
            "facebook.com",
            "www.facebook.com",
            "m.facebook.com",
            "fb.watch",
            "www.fb.watch",
        },
        "vimeo": {"vimeo.com", "www.vimeo.com", "player.vimeo.com"},
        "reddit": {"reddit.com", "www.reddit.com", "old.reddit.com", "v.redd.it"},
        "twitch": {"twitch.tv", "www.twitch.tv", "clips.twitch.tv"},
        "dailymotion": {"dailymotion.com", "www.dailymotion.com", "dai.ly"},
        "soundcloud": {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"},
    }
    MAX_DURATION_SECONDS = 6 * 60 * 60
    MIN_CLIP_SECONDS = 0.4

    def __init__(self) -> None:
        self._ffmpeg = shutil.which("ffmpeg")

    def ensure_ffmpeg(self) -> None:
        """FFmpeg ikilisinin sistemde bulunduğunu doğrular."""
        if not self._ffmpeg:
            self._ffmpeg = shutil.which("ffmpeg")
        if not self._ffmpeg:
            raise MediaServiceError(
                "FFmpeg was not found. Install FFmpeg or run the Docker image."
            )

    def detect_platform(self, url: str) -> str:
        """URL hostuna göre platform adını döndürür."""
        host = (urlparse(url.strip()).hostname or "").lower()
        if host.startswith("www."):
            bare = host[4:]
        else:
            bare = host
        for name, hosts in self.PLATFORM_HOSTS.items():
            if host in hosts or bare in hosts:
                return name
        return "unknown"

    def validate_url(self, url: str) -> str:
        """Desteklenen medya URL'sini doğrular ve normalize eder."""
        if not url or not isinstance(url, str):
            raise MediaServiceError("Please paste a valid media link.")

        cleaned = url.strip()
        parsed = urlparse(cleaned)
        host = (parsed.hostname or "").lower()

        if parsed.scheme not in {"http", "https"} or not host:
            raise MediaServiceError("Invalid media URL.")

        platform = self.detect_platform(cleaned)
        if platform == "unknown":
            raise MediaServiceError(
                "Unsupported platform. Try YouTube, TikTok, Instagram, X/Twitter, "
                "Facebook, Vimeo, Reddit, Twitch, Dailymotion, or SoundCloud."
            )

        if platform == "youtube":
            return self._normalize_youtube(cleaned, host, parsed)

        return cleaned

    def _normalize_youtube(self, cleaned: str, host: str, parsed) -> str:
        """YouTube kısa / shorts / embed bağlantılarını watch URL'sine çevirir."""
        if host in {"youtu.be", "www.youtu.be"}:
            video_id = parsed.path.strip("/").split("/")[0]
            if not re.fullmatch(r"[\w-]{11}", video_id):
                raise MediaServiceError("Could not read the YouTube video ID.")
            return f"https://www.youtube.com/watch?v={video_id}"

        path = parsed.path or ""
        if path.startswith("/shorts/"):
            video_id = path.split("/shorts/")[-1].split("/")[0]
        elif path.startswith("/embed/"):
            video_id = path.split("/embed/")[-1].split("/")[0]
        elif path.startswith("/live/"):
            video_id = path.split("/live/")[-1].split("/")[0]
        else:
            video_id = parse_qs(parsed.query).get("v", [""])[0]

        if not re.fullmatch(r"[\w-]{11}", video_id or ""):
            raise MediaServiceError("This link does not point to a single YouTube video.")

        return f"https://www.youtube.com/watch?v={video_id}"

    def extract_metadata(self, url: str) -> dict[str, Any]:
        """Video başlığı, süre, küçük resim ve kalite seçeneklerini döndürür."""
        safe_url = self.validate_url(url)
        platform = self.detect_platform(safe_url)
        options = self._base_ydl_opts()
        options["skip_download"] = True

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(safe_url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise MediaServiceError(self._friendly_extract_error(str(exc))) from exc
        except Exception as exc:  # noqa: BLE001
            raise MediaServiceError("Could not fetch video info. Check the link and try again.") from exc

        if not info:
            raise MediaServiceError("Video metadata came back empty.")

        if info.get("_type") == "playlist" and not info.get("duration"):
            entries = info.get("entries") or []
            first = next((item for item in entries if item), None)
            if first:
                info = first
            else:
                raise MediaServiceError("Playlists are not supported. Paste a single media link.")

        if info.get("is_live"):
            raise MediaServiceError("Live streams cannot be trimmed or downloaded.")

        raw_duration = info.get("duration")
        timeline_enabled = False
        duration_value: float | None = None
        if raw_duration is not None:
            try:
                duration_value = float(raw_duration)
            except (TypeError, ValueError):
                duration_value = None
            if duration_value is not None and duration_value > 0:
                if duration_value > self.MAX_DURATION_SECONDS:
                    raise MediaServiceError("Videos longer than 6 hours cannot be processed.")
                timeline_enabled = True
                duration_value = round(duration_value, 3)
            else:
                duration_value = None

        qualities = self._collect_qualities(info)
        thumbnail = self._best_thumbnail(info)
        preview_supported = platform == "youtube" and timeline_enabled

        return {
            "ok": True,
            "url": safe_url,
            "id": info.get("id"),
            "title": info.get("title") or "Untitled",
            "uploader": info.get("uploader") or info.get("channel") or info.get("uploader_id") or "Unknown",
            "duration": duration_value,
            "timeline_enabled": timeline_enabled,
            "thumbnail": thumbnail,
            "qualities": qualities,
            "has_audio": self._has_audio(info),
            "platform": platform,
            "preview_supported": preview_supported,
        }

    def download_range(
        self,
        url: str,
        start: float,
        end: float,
        media_type: str,
        quality: int | None,
        duration: float | None = None,
        workdir: str | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> tuple[str, str, str]:
        """Seçilen aralığı indirir; süre yoksa veya tam aralık seçildiyse kesmeden kaydeder."""
        self.ensure_ffmpeg()
        safe_url = self.validate_url(url)
        media_type = (media_type or "mp4").lower().strip()
        if media_type not in {"mp4", "mp3"}:
            raise MediaServiceError("Format must be MP4 or MP3.")

        # Süre bilinmiyorsa timeline kapalı → tam dosya, FFmpeg kesimi yok
        full_file = duration is None
        if full_file:
            start = 0.0
            end = 0.0
            trim_full = True
        else:
            start = max(0.0, float(start))
            end = float(end)
            if end <= start:
                raise MediaServiceError("End time must be greater than start time.")
            if (end - start) < self.MIN_CLIP_SECONDS:
                raise MediaServiceError("The selected range is too short.")

            duration = float(duration)
            end = min(end, duration)
            if start >= duration:
                raise MediaServiceError("Start time is beyond the video duration.")
            trim_full = start <= 0.05 and (duration - end) <= 0.25

        download_cap = 100 if trim_full else 80
        owned_dir = False
        if not workdir:
            workdir = tempfile.mkdtemp(prefix="framecut_")
            owned_dir = True

        self._report(progress_cb, 2, "İndiriliyor…")
        outtmpl = str(Path(workdir) / "%(id)s.%(ext)s")

        options = self._base_ydl_opts()
        options.update(
            {
                "outtmpl": outtmpl,
                "restrictfilenames": True,
                "windowsfilenames": True,
                "merge_output_format": "mp4",
                "overwrites": True,
                "noprogress": False,
                "progress_hooks": [self._make_progress_hook(progress_cb, download_cap)],
            }
        )

        if media_type == "mp3":
            options["format"] = "bestaudio/best"
            options["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
        else:
            options["format"] = self._video_format_selector(quality)

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(safe_url, download=True)
                prepared = ydl.prepare_filename(info)
        except yt_dlp.utils.DownloadError as exc:
            if owned_dir:
                shutil.rmtree(workdir, ignore_errors=True)
            raise MediaServiceError(self._friendly_extract_error(str(exc))) from exc
        except Exception as exc:  # noqa: BLE001
            if owned_dir:
                shutil.rmtree(workdir, ignore_errors=True)
            raise MediaServiceError("An error occurred while downloading or cutting.") from exc

        source = self._resolve_output_file(workdir, prepared, media_type)
        if not source or not os.path.isfile(source):
            if owned_dir:
                shutil.rmtree(workdir, ignore_errors=True)
            raise MediaServiceError("The output file could not be created.")

        if not trim_full:
            self._report(progress_cb, download_cap, "Kesiliyor…")
            try:
                source = self._cut_with_ffmpeg(source, start, end, media_type, progress_cb)
            except MediaServiceError:
                if owned_dir:
                    shutil.rmtree(workdir, ignore_errors=True)
                raise

        self._report(progress_cb, 98, "Dosya hazırlanıyor…")
        source_path = Path(source)
        actual_ext = source_path.suffix.lstrip(".").lower()
        if actual_ext in {"jpg", "jpeg", "png", "webp", "gif"}:
            ext = "jpg" if actual_ext == "jpeg" else actual_ext
            mime = "image/jpeg" if ext == "jpg" else f"image/{ext}"
        else:
            ext = "mp3" if media_type == "mp3" else (actual_ext or "mp4")
            mime = "audio/mpeg" if ext == "mp3" else "video/mp4"
        title = (info or {}).get("title") or "clip"
        download_name = self._safe_download_name(title, ext)
        self._report(progress_cb, 100, "Hazır")
        return source, download_name, mime

    def _report(self, progress_cb: ProgressCallback | None, percent: int, phase: str) -> None:
        """İlerleme geri çağrısını güvenli şekilde tetikler."""
        if progress_cb:
            progress_cb(percent, phase)

    def _make_progress_hook(self, progress_cb: ProgressCallback | None, cap: int):
        """yt-dlp indirme yüzdesini 0-cap aralığına map eden hook üretir."""

        def hook(event: dict[str, Any]) -> None:
            if not progress_cb:
                return
            status = event.get("status")
            if status == "finished":
                self._report(progress_cb, cap, "İndirme tamamlandı")
                return
            if status != "downloading":
                return

            total = event.get("total_bytes") or event.get("total_bytes_estimate") or 0
            done = event.get("downloaded_bytes") or 0
            ratio = 0.0
            if total:
                ratio = min(1.0, done / total)
            else:
                raw = str(event.get("_percent_str") or "").replace("%", "").strip()
                try:
                    ratio = min(1.0, max(0.0, float(raw) / 100.0))
                except ValueError:
                    ratio = 0.0
            percent = max(3, min(cap, int(ratio * cap)))
            self._report(progress_cb, percent, "İndiriliyor…")

        return hook

    def _popen_kwargs(self) -> dict[str, Any]:
        """Windows'ta konsol penceresi açmadan süreç başlatma ayarları."""
        kwargs: dict[str, Any] = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        return kwargs

    def _cut_with_ffmpeg(
        self,
        source: str,
        start: float,
        end: float,
        media_type: str,
        progress_cb: ProgressCallback | None,
    ) -> str:
        """İndirilen dosyayı FFmpeg ile tam olarak IN/OUT aralığına keser."""
        suffix = ".mp3" if media_type == "mp3" else ".mp4"
        dest = str(Path(source).with_name(f"{Path(source).stem}_clip{suffix}"))
        clip = max(end - start, 0.001)

        if media_type == "mp3":
            cmd = [
                self._ffmpeg,
                "-y",
                "-ss",
                f"{start:.3f}",
                "-to",
                f"{end:.3f}",
                "-i",
                source,
                "-vn",
                "-c:a",
                "libmp3lame",
                "-q:a",
                "2",
                "-progress",
                "pipe:1",
                "-nostats",
                dest,
            ]
            self._run_ffmpeg(cmd, clip, progress_cb, dest)
        else:
            copy_cmd = [
                self._ffmpeg,
                "-y",
                "-ss",
                f"{start:.3f}",
                "-to",
                f"{end:.3f}",
                "-i",
                source,
                "-c",
                "copy",
                "-avoid_negative_ts",
                "make_zero",
                "-progress",
                "pipe:1",
                "-nostats",
                dest,
            ]
            copied = self._run_ffmpeg(copy_cmd, clip, progress_cb, dest, raise_on_fail=False)
            if not copied:
                encode_cmd = [
                    self._ffmpeg,
                    "-y",
                    "-ss",
                    f"{start:.3f}",
                    "-to",
                    f"{end:.3f}",
                    "-i",
                    source,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    "-progress",
                    "pipe:1",
                    "-nostats",
                    dest,
                ]
                self._run_ffmpeg(encode_cmd, clip, progress_cb, dest)

        if os.path.isfile(source) and os.path.abspath(source) != os.path.abspath(dest):
            try:
                os.remove(source)
            except OSError:
                pass
        return dest

    def _run_ffmpeg(
        self,
        cmd: list[str],
        clip_seconds: float,
        progress_cb: ProgressCallback | None,
        dest: str,
        raise_on_fail: bool = True,
    ) -> bool:
        """FFmpeg sürecini çalıştırır ve kesim ilerlemesini yayınlar."""
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="ignore",
            **self._popen_kwargs(),
        )
        assert process.stdout is not None
        for line in process.stdout:
            stripped = line.strip()
            elapsed = self._parse_ffmpeg_time(stripped)
            if elapsed is not None:
                fraction = min(1.0, max(0.0, elapsed / clip_seconds))
                self._report(progress_cb, 80 + int(15 * fraction), "Kesiliyor…")
            elif stripped == "progress=end":
                break
        process.wait()
        ok = process.returncode == 0 and os.path.isfile(dest) and os.path.getsize(dest) > 0
        if not ok and raise_on_fail:
            raise MediaServiceError("FFmpeg could not cut the selected range.")
        if ok:
            self._report(progress_cb, 95, "Kesiliyor…")
        return ok

    def _parse_ffmpeg_time(self, line: str) -> float | None:
        """FFmpeg -progress satırından saniye üretir."""
        if line.startswith("out_time=") and not line.startswith("out_time_"):
            value = line.split("=", 1)[1]
            if value in {"N/A", ""}:
                return None
            parts = value.split(":")
            if len(parts) != 3:
                return None
            try:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            except ValueError:
                return None
        return None

    def _base_ydl_opts(self) -> dict[str, Any]:
        """yt-dlp için ortak, sessiz ve güvenli seçenekleri üretir."""
        return {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "ignoreerrors": False,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 30,
            "nocheckcertificate": False,
            "geo_bypass": True,
        }

    STANDARD_HEIGHTS = (2160, 1440, 1080, 720, 480, 360, 240)

    def _collect_qualities(self, info: dict[str, Any]) -> list[int]:
        """Dikey (progressive) çözünürlük etiketlerini standart p değerlerine indirger."""
        found: set[int] = set()
        for fmt in info.get("formats") or []:
            vcodec = fmt.get("vcodec")
            if not vcodec or vcodec == "none":
                continue
            height = fmt.get("height")
            width = fmt.get("width")
            vertical: int | None = None
            if isinstance(height, int) and isinstance(width, int) and height > 0 and width > 0:
                # 1920x1080 → 1080p, 1080x1920 Shorts → 1080p (genişlik/yükseklik min)
                vertical = min(height, width)
            elif isinstance(height, int) and height > 0:
                vertical = height
            if vertical is None or vertical < 144:
                continue
            snapped = self._snap_quality_height(vertical)
            if snapped:
                found.add(snapped)

        return [h for h in self.STANDARD_HEIGHTS if h in found]

    def _snap_quality_height(self, value: int) -> int | None:
        """Ham piksel değerini en yakın standart dikey çözünürlüğe yuvarlar."""
        for standard in self.STANDARD_HEIGHTS:
            if abs(value - standard) <= 32:
                return standard
        candidates = [h for h in self.STANDARD_HEIGHTS if h <= value]
        return max(candidates) if candidates else None

    def _video_format_selector(self, quality: int | None) -> str:
        """İstenen dikey çözünürlüğe göre yt-dlp format ifadesini üretir."""
        if quality and quality > 0:
            height = int(quality)
            return (
                f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
                f"bestvideo[width<={height}][ext=mp4]+bestaudio[ext=m4a]/"
                f"bestvideo[height<={height}]+bestaudio/"
                f"bestvideo[width<={height}]+bestaudio/"
                f"best[height<={height}]/"
                f"best[width<={height}]/"
                "best"
            )
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best"

    def _has_audio(self, info: dict[str, Any]) -> bool:
        """Kaynakta indirilebilir ses izi olup olmadığını kontrol eder."""
        if info.get("acodec") and info.get("acodec") != "none":
            return True
        for fmt in info.get("formats") or []:
            acodec = fmt.get("acodec")
            if acodec and acodec != "none":
                return True
        return False

    def _best_thumbnail(self, info: dict[str, Any]) -> str:
        """En yüksek çözünürlüklü küçük resmi seçer."""
        thumbs = info.get("thumbnails") or []
        if thumbs:
            ranked = sorted(
                thumbs,
                key=lambda item: (item.get("height") or 0) * (item.get("width") or 0),
                reverse=True,
            )
            url = ranked[0].get("url")
            if url:
                return url
        return info.get("thumbnail") or ""

    def _resolve_output_file(self, workdir: str, prepared: str, media_type: str) -> str | None:
        """yt-dlp çıktı şablonundan gerçek dosya yolunu bulur."""
        candidates: list[Path] = []
        prepared_path = Path(prepared)
        stems = {prepared_path.stem, prepared_path.with_suffix("").stem}

        for path in Path(workdir).iterdir():
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if media_type == "mp3" and suffix == ".mp3":
                candidates.append(path)
            elif media_type == "mp4" and suffix in {".mp4", ".mkv", ".webm", ".mov", ".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                candidates.append(path)
            elif path.stem in stems:
                candidates.append(path)

        if not candidates:
            files = [p for p in Path(workdir).iterdir() if p.is_file()]
            candidates = files

        if not candidates:
            return None

        candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        return str(candidates[0])

    def _safe_download_name(self, title: str, ext: str) -> str:
        """Tarayıcıya gönderilecek güvenli dosya adını üretir."""
        cleaned = re.sub(r'[\\/:*?"<>|]+', "_", title)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._")
        cleaned = cleaned[:120] or "clip"
        return f"{cleaned}.{ext}"

    def _friendly_extract_error(self, raw: str) -> str:
        """yt-dlp ham hatalarını kullanıcı dostu mesajlara dönüştürür."""
        lowered = raw.lower()
        if "private" in lowered:
            return "This media is private and cannot be downloaded."
        if "unavailable" in lowered or "not available" in lowered:
            return "This media is unavailable or has been removed."
        if "sign in" in lowered or "confirm your age" in lowered or "age" in lowered or "login" in lowered:
            return "This media is age or login restricted."
        if "unsupported url" in lowered or "no video" in lowered:
            return "Unsupported or invalid link."
        if "http error 429" in lowered or "too many" in lowered:
            return "The platform is rate-limiting requests. Try again in a moment."
        return "Could not fetch the media. Check the link and try again."
