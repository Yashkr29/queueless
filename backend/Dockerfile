FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
COPY models ./models
RUN useradd -m appuser && chown -R appuser /srv
USER appuser
EXPOSE 8000
# Single worker on purpose: the WebSocket hub and rate limiter are in-process (see docs/07-DEPLOYMENT.md §6)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
