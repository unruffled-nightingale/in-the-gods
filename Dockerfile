FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt \
    && python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2')"

COPY server/ server/
COPY frontend/theatre.html frontend/theatre.html
COPY frontend/logo.png frontend/logo.png
COPY data/extracts/latest.json data/extracts/latest.json
COPY data/extracts/latest.embeddings.npz data/extracts/latest.embeddings.npz
COPY data/extracts/latest.venues.json data/extracts/latest.venues.json

EXPOSE 80
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "80"]
