# Backend: Resource Link Hub API (Python murni, tanpa framework)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    DATA_DIR=/var/lib/backend_data \
    DATA_FILE=links.json

# Jalankan sebagai user non-root
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /var/lib/backend_data \
    && chown appuser:appuser /var/lib/backend_data

WORKDIR /app
COPY app.py .

# Pastikan tidak ada syntax error saat build
RUN python -m py_compile app.py

# Docker akan menyalin kepemilikan folder ini ke Named Volume baru
VOLUME ["/var/lib/backend_data"]

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

CMD ["python", "app.py"]
