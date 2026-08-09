# The container Cloud Run runs. Deliberately ordinary — there is nothing
# ADK-specific in here, because there is nothing ADK-specific about shipping a
# FastAPI app.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The agent, the graph, and the front end.
COPY . .

# Cloud Run hands you the port. Never hardcode 8080.
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
