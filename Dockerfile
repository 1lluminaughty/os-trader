# syntax=docker/dockerfile:1.6
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Berlin

WORKDIR /app

# curl for the healthcheck only.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first (cached layer).
COPY requirements.txt .
RUN pip install -r requirements.txt tzdata

# Copy the app source (small surface, fast layer).
COPY app.py data.py signals.py trend_signals.py charts.py warrants.py analysts.py ./

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
