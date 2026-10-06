# nb_graph API (FastAPI). Build context = repository root, so the graph SQL is baked in.
FROM docker.io/python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 GRAPH_SQL_DIR=/app/sql
WORKDIR /app
COPY graph-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY graph-api/app ./app
COPY db/graph ./sql

RUN useradd --system --uid 10001 nbgraph
USER nbgraph
EXPOSE 8090
HEALTHCHECK --interval=15s --timeout=4s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request,json,sys; d=json.load(urllib.request.urlopen('http://127.0.0.1:8090/api/health',timeout=3)); sys.exit(0 if d.get('graph_schema')=='ready' else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090", "--proxy-headers", "--forwarded-allow-ips", "*"]
