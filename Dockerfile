FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MAYBEAI_HEADLESS=1 \
    SDL_VIDEODRIVER=dummy \
    SDL_AUDIODRIVER=dummy

WORKDIR /app

# Install ffmpeg for vertical clip processing and slim runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create non-root user and ensure runtime directories are writable
RUN useradd --create-home --shell /bin/bash maybeai \
    && mkdir -p /app/config /app/data /app/data/clips /app/data/second_brain/streams /app/plugins \
    && chown -R maybeai:maybeai /app

USER maybeai

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/health', timeout=3)" || exit 1

CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "7860"]
