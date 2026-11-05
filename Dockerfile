# Zəka (AzTU Rəqəmsal Kampus) — demo image. Python standard library only: no pip install step.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1
WORKDIR /app
RUN useradd --create-home --uid 10001 zeka && mkdir -p /app/data /app/logs && chown -R zeka:zeka /app
COPY --chown=zeka:zeka . .
USER zeka
EXPOSE 5070
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=6 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5070/api/bootstrap', timeout=2)"
# --reset: every start gives a clean, consistent demo (data is generated relative to today)
CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "5070", "--reset"]
