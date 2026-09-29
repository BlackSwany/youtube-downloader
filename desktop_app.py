"""Atamation Media Downloader masaüstü penceresi."""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

from app import app, _default_save_dir

# WebView2 içinde YouTube embed için Edge benzeri UA
EDGE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
)


class DesktopApi:
    """pywebview JS köprüsü: klasör seçici, pencere kontrolleri ve Masaüstü yolu."""

    def __init__(self) -> None:
        self._window = None
        self._is_maximized = False

    def bind_window(self, window) -> None:
        """Aktif pencere referansını saklar ve durum olaylarını dinler."""
        self._window = window
        try:
            window.events.maximized += self._mark_maximized
            window.events.restored += self._mark_restored
        except Exception:
            pass

    def _mark_maximized(self) -> None:
        """Native maximize olayından sonra bayrağı günceller."""
        self._is_maximized = True

    def _mark_restored(self) -> None:
        """Pencere normale dönünce maximize bayrağını sıfırlar."""
        self._is_maximized = False

    def get_desktop_path(self) -> str:
        """Varsayılan kayıt klasörünü (Masaüstü) döndürür."""
        return str(_default_save_dir())

    def select_folder(self) -> str | None:
        """Klasör seçim diyaloğunu açar."""
        import webview

        if self._window is None:
            return None
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        if isinstance(result, (list, tuple)):
            return result[0] if result else None
        return str(result)

    def minimize(self) -> None:
        """Pencereyi görev çubuğuna küçültür."""
        if self._window is None:
            return
        self._window.minimize()

    def toggle_maximize(self) -> bool:
        """Tam ekran (maximize) ile normal boyut arasında geçer."""
        if self._window is None:
            return False
        if self._is_maximized:
            self._window.restore()
            self._is_maximized = False
        else:
            self._window.maximize()
            self._is_maximized = True
        return self._is_maximized

    def is_maximized(self) -> bool:
        """Pencerenin büyütülmüş olup olmadığını döndürür."""
        return bool(self._is_maximized)

    def close(self) -> None:
        """Uygulama penceresini kapatır."""
        if self._window is None:
            return
        self._window.destroy()


def resource_paths() -> list[Path]:
    """Exe, _MEIPASS ve geliştirme köklerini döndürür."""
    paths: list[Path] = []
    if getattr(sys, "frozen", False):
        paths.append(Path(sys.executable).resolve().parent)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            paths.append(Path(meipass))
    paths.append(Path(__file__).resolve().parent)
    return paths


def prepend_ffmpeg_path() -> None:
    """Paketlenmiş veya sistem FFmpeg'ini PATH'in başına ekler."""
    for root in resource_paths():
        for folder in (root / "ffmpeg", root):
            binary = folder / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
            if binary.is_file():
                os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
                return


def unused_port() -> int:
    """127.0.0.1 üzerinde boş bir TCP portu seçer."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until_up(url: str, timeout: float = 20.0) -> None:
    """Flask ayağa kalkana kadar kısa aralıklarla dener."""
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=0.4)
            return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.2)
    raise RuntimeError("Atamation sunucusu başlatılamadı.")


def main() -> None:
    """Yerel sunucuyu açar ve masaüstü penceresini gösterir."""
    prepend_ffmpeg_path()
    port = unused_port()
    url = f"http://127.0.0.1:{port}/"

    thread = threading.Thread(
        target=lambda: app.run(
            host="127.0.0.1",
            port=port,
            debug=False,
            threaded=True,
            use_reloader=False,
        ),
        daemon=True,
        name="atamation-flask",
    )
    thread.start()
    wait_until_up(f"http://127.0.0.1:{port}/api/health")

    try:
        import webview
    except ImportError as exc:
        raise SystemExit(
            "pywebview kurulu değil. Masaüstü için: pip install pywebview"
        ) from exc

    api = DesktopApi()
    window = webview.create_window(
        "Atamation Media Downloader",
        url,
        js_api=api,
        width=1320,
        height=860,
        min_size=(960, 680),
        background_color="#070B14",
        text_select=True,
        frameless=True,
        easy_drag=False,
        shadow=True,
    )
    api.bind_window(window)
    # private_mode=True (varsayılan) YouTube embed'i WebView2'de boş bırakabiliyor
    webview.start(private_mode=False, user_agent=EDGE_USER_AGENT)


if __name__ == "__main__":
    main()
