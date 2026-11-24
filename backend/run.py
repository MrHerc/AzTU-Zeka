"""Start the AzTU Rəqəmsal Kampus demo:  python backend/run.py [--port 5070] [--reset] [--public-url https://zeka.example.az]"""
import argparse
import gc
import os
import re
import signal
import socket
import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent  # repository: frontend/, content/, data/, logs/
sys.path.insert(0, str(BACKEND))

from zeka.core import clock, config, jobs, mail, migrate  # noqa: E402
from zeka.legacy import api, store  # noqa: E402
from zeka.core.security import CFG, LOOPBACK  # noqa: E402
from zeka.core import web  # noqa: E402
from zeka.core.web import make_server  # noqa: E402

LOG_MAX = 5 * 1024 * 1024
JOBS_ON = os.environ.get("ZEKA_JOBS", "1") != "0"         # the periodic jobs (Task 36); 0 turns the runner off
try:
    JOBS_DELAY = float(os.environ.get("ZEKA_JOBS_DELAY", "15"))   # seconds after start before the first cycle
except ValueError:
    sys.exit("ZEKA_JOBS_DELAY saniyə sayı olmalıdır (məs. 15)")


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
    if clock.ZONE is None:
        ap.error(f"ZEKA_TZ={clock.TZ_NAME}: saat qurşağı tapılmadı (məs. Asia/Baku; Windows-da tzdata paketi lazımdır)")
    if config.prod():
        if args.reset:
            ap.error("prod rejimində --reset qadağandır: məlumat heç vaxt silinmir")
        if exposed and not public:
            ap.error("prod rejimində şəbəkədə PUBLIC_URL təyin edin (məs. https://zeka.aztu.edu.az): sənədlərin QR kodları, "
                     "Secure cookie və HSTS ondan asılıdır")
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
        mail.settings()                       # a wrong e-mail setting stops the start, not every message later (Checkpoint D, SF-5)
    except mail.MailConfigError as ex:
        ap.error(f"e-poçt ayarı: {ex}")
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
    if exposed and not CFG.access_code and not config.prod():      # prod has no demo login to protect
        shown += "  ·  DİQQƏT: giriş kodu yoxdur (ZEKA_ALLOW_OPEN_DEMO=1)"
    if args.workers > 1:
        shown += f"  ·  {args.workers} proses"
    print(f"AzTU Rəqəmsal Kampus ({config.MODE}): http://127.0.0.1:{args.port}{shown}  (dayandırmaq üçün Ctrl+C)", flush=True)
    if args.workers == 1:
        srv = make_server(args.port, api.R, ROOT / "frontend", api.before, api.after, log, host=args.host)
        done = threading.Event()
        if JOBS_ON:     # shortcut: one process runs the jobs in a thread; with --workers the supervisor gives them a process
            threading.Thread(target=run_jobs, args=(log, done.is_set), daemon=True, name="jobs").start()
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            done.set()
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


def run_jobs(log, stop):
    """The periodic jobs (Task 36): one runner at a time across processes, by the lease in the database."""
    from zeka.legacy import periodic  # noqa: F401  registers the jobs
    jobs.loop(store.connect, f"{socket.gethostname()}:{os.getpid()}", stop=stop, log=log, first_delay=JOBS_DELAY)


def runner(log):
    """The job runner's own process, restarted by the supervisor like a worker."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    done = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: done.set())
    run_jobs(log, done.is_set)


def supervise(args, log):
    """Start the workers, restart any that dies, stop them all on SIGTERM or Ctrl+C."""
    children: dict[int, float] = {}
    jobs_pid = [0]                                             # the job runner (Task 36), restarted like a worker
    stopping = False

    def spawn(kind="worker"):
        if stopping:                                           # a stop request wins over a restart
            return
        pid = os.fork()
        if pid == 0:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)      # not the supervisor's stop(); worker() sets its own when serving
            code = 0
            try:
                runner(log) if kind == "jobs" else worker(args, log)
            except BaseException as ex:                        # noqa: BLE001  a worker must never return into the supervisor loop
                log(f"{kind} {os.getpid()} failed: {type(ex).__name__}: {ex}")
                print(f"{kind} {os.getpid()} failed: {type(ex).__name__}: {ex}", file=sys.stderr, flush=True)
                code = 1
            os._exit(code)
        children[pid] = time.monotonic()
        if kind == "jobs":
            jobs_pid[0] = pid

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
    if JOBS_ON:
        spawn("jobs")
    fast, gave_up, runner_fails = 0, False, 0
    while children:
        try:
            pid, status = os.wait()
        except ChildProcessError:
            break
        started = children.pop(pid, None)
        if stopping or started is None:
            continue
        if pid == jobs_pid[0]:                               # the runner: restarted on its own, never counted against the workers
            runner_fails = runner_fails + 1 if time.monotonic() - started < 60 else 0
            wait = min(60, 2 ** runner_fails)                # a runner that keeps failing is restarted ever more slowly (PY-14)
            log(f"job runner {pid} exited (status {status}); restarting in {wait} s")
            time.sleep(wait)
            spawn("jobs")
            continue
        log(f"worker {pid} exited (status {status}); restarting")
        if time.monotonic() - started < 2:                   # a worker that dies at once: do not spin
            fast += 1
            if fast >= 3 * args.workers:                     # it will not get better by itself: stop and say why
                msg = "işçilər başlaya bilmir (ardıcıl uğursuz başlanğıclar); səbəb: logs/errors.log və yuxarıdakı xəta"
                log(msg)
                print(msg, file=sys.stderr, flush=True)
                gave_up = True
                stop()
                continue
            time.sleep(1)
        else:
            fast = 0
        spawn()
    if gave_up:
        sys.exit(1)


if __name__ == "__main__":
    main()
