"""
Resource Link Hub - Backend REST API
Kelompok F - Cloud Computing (Ujian Chunin)

REST API sederhana tanpa framework (hanya standard library Python) untuk
menyimpan tautan modul, slide, dan materi praktikum.

Endpoint:
    GET    /health              -> status layanan & storage
    GET    /links               -> daftar seluruh tautan
    POST   /links               -> tambah tautan baru (body JSON)
    DELETE /links?index=X       -> hapus tautan pada index X

Data disimpan dalam file JSON (links.json) di dalam Docker Named Volume
(default: /var/lib/backend_data), sehingga tetap aman walaupun kontainer
dihapus (docker rm -f) dan dibuat ulang.
"""

import json
import os
import signal
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# Konfigurasi (bisa di-override lewat environment variable)
# ---------------------------------------------------------------------------
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
DATA_DIR = os.environ.get("DATA_DIR", "/var/lib/backend_data")
DATA_FILE = os.path.join(DATA_DIR, os.environ.get("DATA_FILE", "links.json"))
APP_VERSION = os.environ.get("APP_VERSION", "dev")

MAX_BODY_BYTES = 16 * 1024
CATEGORIES = ["Modul", "Slide", "Video", "Repositori", "Lainnya"]
LIMITS = {"title": 120, "url": 2048, "description": 500}

_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------
def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_links():
    """Baca seluruh tautan dari file JSON. File belum ada -> list kosong."""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        # File rusak: jangan crash, cukup log dan anggap kosong.
        log(f"WARNING: gagal membaca {DATA_FILE}: {exc}")
        return []
    return data if isinstance(data, list) else []


def save_links(links):
    """Tulis secara atomik: tulis ke file sementara lalu rename.

    Dengan cara ini file links.json tidak akan pernah setengah tertulis
    walaupun kontainer dimatikan paksa di tengah proses penyimpanan.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=DATA_DIR, prefix=".links-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(links, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, DATA_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def storage_writable():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        return os.access(DATA_DIR, os.W_OK)
    except OSError:
        return False


def log(message):
    print(f"[{_now_iso()}] {message}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Validasi input
# ---------------------------------------------------------------------------
class ValidationError(Exception):
    pass


def validate_link(payload):
    if not isinstance(payload, dict):
        raise ValidationError("Body harus berupa objek JSON.")

    title = str(payload.get("title", "")).strip()
    url = str(payload.get("url", "")).strip()
    category = str(payload.get("category", "Lainnya")).strip() or "Lainnya"
    description = str(payload.get("description", "")).strip()

    if not title:
        raise ValidationError("Field 'title' wajib diisi.")
    if not url:
        raise ValidationError("Field 'url' wajib diisi.")

    parsed = urlparse(url)
    host = parsed.hostname or ""
    if (
        parsed.scheme not in ("http", "https")
        or not host
        or not (host == "localhost" or "." in host)
        or any(ch.isspace() for ch in url)
    ):
        raise ValidationError("Field 'url' harus diawali http:// atau https:// dengan domain yang valid.")

    if category not in CATEGORIES:
        raise ValidationError(f"Field 'category' harus salah satu dari: {', '.join(CATEGORIES)}.")

    for field, value in (("title", title), ("url", url), ("description", description)):
        if len(value) > LIMITS[field]:
            raise ValidationError(f"Field '{field}' maksimal {LIMITS[field]} karakter.")

    return {
        "title": title,
        "url": url,
        "category": category,
        "description": description,
        "created_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class LinkHubHandler(BaseHTTPRequestHandler):
    server_version = "LinkHub/1.0"

    # ---- util -------------------------------------------------------------
    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, status, message):
        self._send_json(status, {"status": "error", "code": status, "message": message})

    def _cors_headers(self):
        # Frontend memakai reverse proxy Nginx (same-origin), CORS hanya
        # untuk kemudahan pengujian langsung ke port 8000.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _route(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        return path, parse_qs(parsed.query)

    def log_message(self, fmt, *args):
        log(f"{self.address_string()} {fmt % args}")

    # ---- methods ----------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path, _ = self._route()
        if path == "/":
            return self._send_json(200, {
                "service": "Resource Link Hub API",
                "version": APP_VERSION,
                "endpoints": ["GET /health", "GET /links", "POST /links", "DELETE /links?index=X"],
            })
        if path == "/health":
            with _lock:
                total = len(load_links())
            writable = storage_writable()
            return self._send_json(200 if writable else 503, {
                "status": "ok" if writable else "degraded",
                "version": APP_VERSION,
                "storage": {"file": DATA_FILE, "writable": writable},
                "total_links": total,
                "time": _now_iso(),
            })
        if path == "/links":
            with _lock:
                links = load_links()
            return self._send_json(200, {
                "status": "success",
                "count": len(links),
                "categories": CATEGORIES,
                "data": links,
            })
        return self._error(404, f"Endpoint '{path}' tidak ditemukan.")

    def do_POST(self):
        path, _ = self._route()
        if path != "/links":
            if path in ("/health", "/"):
                return self._error(405, f"Method POST tidak diizinkan pada '{path}'.")
            return self._error(404, f"Endpoint '{path}' tidak ditemukan.")

        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            return self._error(415, "Content-Type harus application/json.")

        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return self._error(400, "Header Content-Length tidak valid.")
        if length <= 0:
            return self._error(400, "Body request kosong.")
        if length > MAX_BODY_BYTES:
            return self._error(413, f"Body terlalu besar (maks {MAX_BODY_BYTES} byte).")

        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._error(400, "Body bukan JSON yang valid.")

        try:
            link = validate_link(payload)
        except ValidationError as exc:
            return self._error(400, str(exc))

        with _lock:
            links = load_links()
            links.append(link)
            save_links(links)
            index = len(links) - 1

        log(f"Tautan ditambahkan: index={index} title={link['title']!r}")
        return self._send_json(201, {
            "status": "success",
            "message": "Tautan berhasil ditambahkan.",
            "index": index,
            "data": link,
        })

    def do_DELETE(self):
        path, query = self._route()
        if path != "/links":
            if path in ("/health", "/"):
                return self._error(405, f"Method DELETE tidak diizinkan pada '{path}'.")
            return self._error(404, f"Endpoint '{path}' tidak ditemukan.")

        if "index" not in query:
            return self._error(400, "Parameter query 'index' wajib diisi, contoh: /links?index=0")
        raw_index = query["index"][0].strip()
        try:
            index = int(raw_index)
        except ValueError:
            return self._error(400, f"Index '{raw_index}' bukan bilangan bulat.")
        if index < 0:
            return self._error(400, "Index tidak boleh negatif.")

        with _lock:
            links = load_links()
            if index >= len(links):
                return self._error(404, f"Tautan dengan index {index} tidak ditemukan (total {len(links)}).")
            removed = links.pop(index)
            save_links(links)

        log(f"Tautan dihapus: index={index} title={removed.get('title')!r}")
        return self._send_json(200, {
            "status": "success",
            "message": "Tautan berhasil dihapus.",
            "data": removed,
        })

    def do_PUT(self):
        self._error(405, "Method PUT tidak didukung.")

    do_PATCH = do_PUT


def _handle_sigterm(signum, frame):
    raise KeyboardInterrupt


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), LinkHubHandler)
    # docker stop mengirim SIGTERM -> matikan server dengan rapi (tanpa tunggu 10 detik)
    signal.signal(signal.SIGTERM, _handle_sigterm)
    log(f"Resource Link Hub API v{APP_VERSION} berjalan di http://{HOST}:{PORT} (data: {DATA_FILE})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Menerima sinyal stop, server dimatikan.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
