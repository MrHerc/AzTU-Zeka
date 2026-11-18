"""Start the AzTU Rəqəmsal Kampus demo:  python backend/run.py [--port 5070] [--reset] [--public-url https://zeka.example.az]"""
import argparse
import gc
import os
import re
import signal
import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent  # repository: frontend/, content/, data/, logs/
sys.path.insert(0, str(BACKEND))

from zeka.core import clock, config, migrate  # noqa: E402
from zeka.legacy import api, store  # noqa: E402
from zeka.core.security import CFG, LOOPBACK  # noqa: E402
from zeka.core import web  # noqa: E402
from zeka.core.web import make_server  # noqa: E402

LOG_MAX = 5 * 1024 * 1024


def normalize_public_url(value: str) -> str:
    """Scheme + host (+ port) of the public address, without a trailing slash; "" when not set.

    Render supplies PUBLIC_URL as a bare host (e.g. zeka-aztu.onrender.com); its external endpoint is always HTTPS.
    """
    public = (value or "").strip().rstrip("/")
    if public and not re.match(r"https?://", public):
        public = "https://" + public
    if public and not re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d{1,5})?", public):
        raise ValueError("--public-url yalnız sxem və hostdan ibarət olmalıdır, məs. https://zeka.example.az")
    return public


def main():
    # Output redirected to a file or pipe gets the Windows ANSI code page (cp1251/cp1252), which has no "ə": the help text
    # and the start banner then raise UnicodeEncodeError and the server dies at once. UTF-8 encodes every character.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description="AzTU Rəqəmsal Kampus (Zəka) — lokal demo")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5070")))
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"),
                    help="dinləmə ünvanı (serverdə 0.0.0.0, lokal demoda 127.0.0.1)")
    ap.add_argument("--reset", action="store_true", help="demo məlumatlarını sıfırdan yarat")
    ap.add_argument("--public-url", default=os.environ.get("PUBLIC_URL", ""), metavar="URL",
                    help="serverdə portalın ictimai ünvanı (məs. https://zeka.example.az): sənədlərin QR kodları bu ünvana yönəlir")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("ZEKA_WORKERS", "1")),
                    help="eyni portu paylaşan proseslərin sayı (Linux/macOS; susmaya görə 1)")
    args = ap.parse_args()
    if not 1 <= args.workers <= 64:
        ap.error("--workers 1 ilə 64 arasında olmalıdır")
    if args.workers > 1 and not hasattr(os, "fork"):
        ap.error("--workers > 1 yalnız Linux və macOS-da işləyir")
    try:
        public = normalize_public_url(args.public_url)
    except ValueError as ex:
        ap.error(str(ex))
    exposed = args.host not in LOOPBACK
    if config.MODE not in config.MODES:
        ap.error(f"ZEKA_MODE={config.MODE}: yalnız demo və ya prod ola bilər")
    if config.prod():
        if args.reset:
            ap.error("prod rejimində --reset qadağandır: məlumat heç vaxt silinmir")
        if clock.ZONE is None:
            ap.error(f"ZEKA_TZ={clock.TZ_NAME}: saat qurşağı tapılmadı (məs. Asia/Baku; Windows-da tzdata paketi lazımdır)")
        if public.startswith("https://") and CFG.proxy_hops == 0:
            ap.error("PUBLIC_URL https:// ilə başlayır, amma ZEKA_PROXY_HOPS=0: tətbiq TLS danışmır, deməli qabaqda proksi var; "
                     "proksilərin sayını təyin edin (adətən 1)")
    elif exposed and os.environ.get("ZEKA_ALLOW_OPEN_DEMO") != "1":
        # The demo login is password-less: a reachable host runs ZEKA_MODE=prod, or a demo whose risk the operator accepted.
        ap.error(f"--host {args.host}: demo rejimi şəbəkəyə açılmır. Real yerləşdirmə üçün ZEKA_MODE=prod; demonu şəbəkədə "
                 "göstərmək üçün riski qəbul edib ZEKA_ALLOW_OPEN_DEMO=1 və ZEKA_ACCESS_CODE təyin edin")
    CFG.https = public.startswith("https://")
    if public:
        CFG.allowed_hosts = {public.split("://", 1)[1].lower()}
    CFG.access_log = os.environ.get("ZEKA_ACCESS_LOG", "1" if exposed else "0") == "1"
    try:
        store.init(reset=args.reset)
    except migrate.MigrationError as ex:     # files and database disagree: never start on a guessed schema
        sys.exit(f"Verilənlər bazasının sxemi: {ex}")
    api.BASE_URL["value"] = public or f"http://127.0.0.1:{args.port}"
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)

    def log(msg):
        path = log_dir / "errors.log"
        if path.exists() and path.stat().st_size > LOG_MAX:      # keep one previous file; the log cannot fill the disk
            path.replace(log_dir / "errors.log.1")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{clock.local():%Y-%m-%d %H:%M:%S}] {msg}\n")

    shown = f"  ·  ictimai ünvan: {public}" if public else ""
    if exposed and not CFG.access_code:
        shown += "  ·  DİQQƏT: giriş kodu yoxdur (ZEKA_ALLOW_OPEN_DEMO=1)"
    if args.workers > 1:
        shown += f"  ·  {args.workers} proses"
    print(f"AzTU Rəqəmsal Kampus ({config.MODE}): http://127.0.0.1:{args.port}{shown}  (dayandırmaq üçün Ctrl+C)", flush=True)
    if args.workers == 1:
        srv = make_server(args.port, api.R, ROOT / "frontend", api.before, api.after, log, host=args.host)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            srv.server_close()
        return
    supervise(args, log)


def worker(args, log):
    """One forked worker: bring the inherited search indexes up to date, then bind the shared port; stop on SIGTERM."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)            # Ctrl+C reaches the supervisor, which stops the workers
    c = store.connect()
    try:
        store.sync_indexes(c)       # built once by the supervisor (store.init); a restarted worker applies what changed since
    finally:
        c.close()
    srv = make_server(args.port, api.R, ROOT / "frontend", api.before, api.after, log, host=args.host, reuse_port=True)
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    try:
        srv.serve_forever()
    finally:
        srv.server_close()                                   # stop accepting, then let the running handlers finish
        web.drain()


def supervise(args, log):
    """Start the workers, restart any that dies, stop them all on SIGTERM or Ctrl+C."""
    children: dict[int, float] = {}
    stopping = False

    def spawn():
        pid = os.fork()
        if pid == 0:
            code = 0
            try:
                worker(args, log)
            except BaseException as ex:                        # noqa: BLE001  a worker must never return into the supervisor loop
                log(f"worker {os.getpid()} failed: {type(ex).__name__}: {ex}")
                code = 1
            os._exit(code)
        children[pid] = time.monotonic()

    def stop(*_):
        nonlocal stopping
        stopping = True
        for pid in list(children):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    gc.freeze()             # the cyclic GC would write to every inherited index object and unshare its pages in each worker
    for _ in range(args.workers):
        spawn()
    while children:
        try:
            pid, status = os.wait()
        except ChildProcessError:
            break
        started = children.pop(pid, None)
        if stopping or started is None:
            continue
        log(f"worker {pid} exited (status {status}); restarting")
        if time.monotonic() - started < 2:                   # a worker that dies at once: do not spin
            time.sleep(1)
        spawn()


if __name__ == "__main__":
    main()
