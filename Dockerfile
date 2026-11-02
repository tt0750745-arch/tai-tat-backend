FROM node:24-bookworm-slim AS nodejs
FROM python:3.12-slim-bookworm
COPY --from=nodejs /usr/local/bin/node /usr/local/bin/node
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home appuser
COPY app.py runner.py ./
USER appuser
ENV PORT=10000 PYTHONUNBUFFERED=1
EXPOSE 10000
CMD ["python", "app.py"]
