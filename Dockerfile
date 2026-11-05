FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libwps-tools && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd -u 10001 -m app && mkdir /data && chown app:app /data
COPY --chown=app:app . .
USER app
EXPOSE 8080
CMD ["python", "bootstrap.py"]
