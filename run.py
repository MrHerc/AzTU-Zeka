"""Start the AzTU Rəqəmsal Kampus demo:  python run.py [--port 5070] [--reset] [--public-url https://zeka.example.az]"""
import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app import api, store  # noqa: E402
from app.security import CFG, LOOPBACK  # noqa: E402
from app.web import make_server  # noqa: E402

LOG_MAX = 5 * 1024 * 1024


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
    args = ap.parse_args()
    public = args.public_url.strip().rstrip("/")
    # Render supplies PUBLIC_URL as a bare host (e.g. zeka-aztu.onrender.com); its external endpoint is always HTTPS.
    if public and not re.match(r"https?://", public):
        public = "https://" + public
    if public and not re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d{1,5})?", public):
        ap.error("--public-url yalnız sxem və hostdan ibarət olmalıdır, məs. https://zeka.example.az")
    exposed = args.host not in LOOPBACK
    # The demo login is password-less: on a reachable host it must sit behind the shared access code (ZEKA_ACCESS_CODE).
    if exposed and not CFG.access_code and os.environ.get("ZEKA_ALLOW_OPEN_DEMO") != "1":
        ap.error(f"--host {args.host} portalı şəbəkəyə açır: ZEKA_ACCESS_CODE mühit dəyişənini təyin edin "
                 "(və ya riski qəbul edib ZEKA_ALLOW_OPEN_DEMO=1)")
    CFG.https = public.startswith("https://")
    if public:
        CFG.allowed_hosts = {public.split("://", 1)[1].lower()}
    CFG.access_log = os.environ.get("ZEKA_ACCESS_LOG", "1" if exposed else "0") == "1"
    store.init(reset=args.reset)
    api.BASE_URL["value"] = public or f"http://127.0.0.1:{args.port}"
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)

    def log(msg):
        path = log_dir / "errors.log"
        if path.exists() and path.stat().st_size > LOG_MAX:      # keep one previous file; the log cannot fill the disk
            path.replace(log_dir / "errors.log.1")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")

    srv = make_server(args.port, api.R, ROOT / "static", api.before, api.after, log, host=args.host)
    shown = f"  ·  ictimai ünvan: {public}" if public else ""
    if exposed and not CFG.access_code:
        shown += "  ·  DİQQƏT: giriş kodu yoxdur (ZEKA_ALLOW_OPEN_DEMO=1)"
    print(f"AzTU Rəqəmsal Kampus demo: http://127.0.0.1:{args.port}{shown}  (dayandırmaq üçün Ctrl+C)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
