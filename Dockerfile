FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# The bot runs as uid 1000; deploy.sh makes ./data on the host owned by that uid.
RUN useradd --uid 1000 --create-home bot && mkdir -p /data && chown bot:bot /data
USER bot

CMD ["python", "-m", "app.main"]
