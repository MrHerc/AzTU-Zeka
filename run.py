"""Start the AzTU Rəqəmsal Kampus demo:  python run.py [--port 5070] [--reset] [--public-url https://zeka.example.az]"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app import api, store  # noqa: E402
from app.web import make_server  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="AzTU Rəqəmsal Kampus (Zəka) — lokal demo")
    ap.add_argument("--port", type=int, default=5070)
    ap.add_argument("--reset", action="store_true", help="demo məlumatlarını sıfırdan yarat")
    ap.add_argument("--public-url", default="", metavar="URL",
                    help="serverdə portalın ictimai ünvanı (məs. https://zeka.example.az): sənədlərin QR kodları bu ünvana yönəlir")
    args = ap.parse_args()
    public = args.public_url.strip().rstrip("/")
    if public and not re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d{1,5})?", public):
        ap.error("--public-url yalnız sxem və hostdan ibarət olmalıdır, məs. https://zeka.example.az")
    store.init(reset=args.reset)
    api.BASE_URL["value"] = public or f"http://127.0.0.1:{args.port}"
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)

    def log(msg):
        with open(log_dir / "errors.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")

    srv = make_server(args.port, api.R, ROOT / "static", api.before, api.after, log)
    shown = f"  ·  ictimai ünvan: {public}" if public else ""
    print(f"AzTU Rəqəmsal Kampus demo: http://127.0.0.1:{args.port}{shown}  (dayandırmaq üçün Ctrl+C)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
