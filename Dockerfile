# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8080

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8080
CMD ["sh", "-c", "ha-streamdeck-gui serve --host 0.0.0.0 --port ${PORT:-8080}"]
