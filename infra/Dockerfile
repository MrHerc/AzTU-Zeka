# Zəka (AzTU Rəqəmsal Kampus). Python standard library only: no pip install step.
# Production: infra/compose.yml (Caddy + this image, ZEKA_MODE=prod); demo: infra/compose.demo.yml.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 TZ=Asia/Baku \
    ZEKA_DATA=/var/lib/zeka/data BACKUP_DIR=/var/lib/zeka/backups
# tzdata: TZ and ZEKA_TZ need the zone files; openssl and ssh: infra/backup.sh encrypts and sends to the second host
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata openssl openssh-client \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 10001 --home-dir /var/lib/zeka --create-home --shell /usr/sbin/nologin zeka \
 && mkdir -p /var/lib/zeka/data /var/lib/zeka/backups /app/logs \
 && chown -R zeka:zeka /var/lib/zeka /app/logs
WORKDIR /app
# The code belongs to root: the server process (zeka) cannot change it
COPY . .
USER zeka
EXPOSE 5070
HEALTHCHECK --interval=10s --timeout=3s --start-period=90s --retries=6 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5070/healthz', timeout=2)"]
CMD ["python", "backend/run.py", "--host", "0.0.0.0", "--port", "5070"]
