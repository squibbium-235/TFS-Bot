FROM python:3.13-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY src ./src

RUN groupadd \
        --system \
        --gid 10001 \
        tfsbot \
    && useradd \
        --system \
        --uid 10001 \
        --gid tfsbot \
        --home-dir /app \
        --shell /usr/sbin/nologin \
        tfsbot \
    && mkdir -p /app/data \
    && chown -R tfsbot:tfsbot /app

USER tfsbot

CMD ["python", "-m", "src.main"]