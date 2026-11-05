"""run.py — command line, public URL handling and a real start-up of the entry point used by Render."""
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import run  # noqa: E402


@pytest.mark.parametrize("value, out", [
    ("", ""), ("  ", ""), ("zeka-aztu.onrender.com", "https://zeka-aztu.onrender.com"), ("https://zeka.example.az/", "https://zeka.example.az"),
    ("http://127.0.0.1:5070", "http://127.0.0.1:5070"), (" https://a.b.az:8443 ", "https://a.b.az:8443"),
])
def test_normalize_public_url(value, out):
    assert run.normalize_public_url(value) == out


@pytest.mark.parametrize("value", ["https://zeka.example.az/path", "javascript:alert(1)", "https://x.az?q=1", "https://bad host", "https://x.az:123456"])
def test_normalize_public_url_rejects_anything_but_scheme_and_host(value):
    with pytest.raises(ValueError):
        run.normalize_public_url(value)


def _env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PORT", "HOST", "PUBLIC_URL") and not k.startswith("AZTU_LLM_")}
    env.update(extra)
    return env


@pytest.mark.slow
def test_help_survives_a_non_utf8_output_stream():
    # Windows gives redirected output the ANSI code page, which has no "ə"; the help text used to crash with UnicodeEncodeError
    p = subprocess.run([sys.executable, str(ROOT / "run.py"), "--help"], env=_env(PYTHONIOENCODING="cp1251"), capture_output=True, timeout=120)
    assert p.returncode == 0 and "sıfırdan" in p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")[-300:]


@pytest.mark.slow
def test_invalid_public_url_is_a_usage_error(tmp_path):
    p = subprocess.run([sys.executable, str(ROOT / "run.py"), "--public-url", "https://x.az/path"], env=_env(), capture_output=True, timeout=120, cwd=tmp_path)
    assert p.returncode == 2 and "sxem və hostdan" in p.stderr.decode("utf-8", "replace")


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.slow
def test_server_starts_from_a_clean_checkout_like_on_render(tmp_path):
    """The Render start command on an empty disk: seeds the database, serves the portal, uses PORT/HOST/PUBLIC_URL."""
    app_dir = tmp_path / "zeka"
    for name in ("app", "static", "content"):
        shutil.copytree(ROOT / name, app_dir / name, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(ROOT / "run.py", app_dir / "run.py")
    port = _free_port()
    env = _env(PORT=str(port), HOST="127.0.0.1", PUBLIC_URL="zeka-aztu.onrender.com", PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen([sys.executable, "run.py"], cwd=app_dir, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        deadline = time.time() + 60
        while True:
            try:
                with opener.open(f"http://127.0.0.1:{port}/api/bootstrap", timeout=5) as r:
                    boot = r.read().decode()
                break
            except OSError:
                if proc.poll() is not None or time.time() > deadline:
                    raise AssertionError(proc.stderr.read().decode("utf-8", "replace")[-500:]) from None
                time.sleep(0.2)
        assert '"base_url": "https://zeka-aztu.onrender.com"' in boot
        with opener.open(urllib.request.Request(f"http://127.0.0.1:{port}/", method="HEAD"), timeout=5) as r:      # Render health check
            assert r.status == 200
        assert (app_dir / "data" / "campus.db").exists()
    finally:
        proc.send_signal(signal.SIGINT if os.name != "nt" else signal.SIGTERM)
        out, err = proc.communicate(timeout=30)
    assert f"http://127.0.0.1:{port}" in out.decode("utf-8") and "ictimai ünvan: https://zeka-aztu.onrender.com" in out.decode("utf-8")
    assert proc.returncode in (0, -signal.SIGINT, 1) and b"Traceback" not in err
