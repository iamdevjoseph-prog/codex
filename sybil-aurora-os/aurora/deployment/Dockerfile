FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY sybil-aurora-os/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Source
COPY sybil-aurora-os/ ./

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Non-root execution
RUN useradd -m -u 1001 sybil
USER sybil

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "aurora.services.app:app", "--host", "0.0.0.0", "--port", "8000"]
