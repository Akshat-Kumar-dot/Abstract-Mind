FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# OpenCV (used by the OCR engine) needs these system libraries
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend/app backend/app
COPY web web

RUN useradd --create-home app && chown -R app /srv
USER app

# Render sets PORT; 10000 is its default. Requests only reach the app through
# Render's proxy, so its X-Forwarded-For is trusted: rate limits then count
# each visitor's real address instead of the proxy's.
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips '*'"]
