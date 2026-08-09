# The venue's container. Cloud Run builds this with `gcloud run deploy --source .`
# from ./deploy-venue.sh.
#
# NOT the agent's — that one lives in solutions/step10_deploy/Dockerfile and is
# copied into agent/ by use-solution.sh. Two services, two images.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The venue is one module plus its two static files.
COPY venue/ ./venue/

# Cloud Run hands you the port. Never hardcode 8080.
CMD exec uvicorn venue.app:app --host 0.0.0.0 --port ${PORT:-8080}
