FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /opt/lab
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system lab \
    && useradd --system --gid lab --home-dir /opt/lab lab \
    && mkdir -p /data \
    && chown lab:lab /data

COPY app ./app
COPY bot ./bot

USER lab
ENV LAB_DB_PATH=/data/lab.db
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
