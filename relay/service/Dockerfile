# The registration service, as the relay box runs it: next to frps, on loopback, its file on a volume.
#   docker build -t home-hub/relay-service relay/service
FROM python:3.13-slim
WORKDIR /srv/relay
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY registry.py app.py cli.py ./
ENV RELAY_DATA=/data RELAY_PORT=7100 PYTHONUNBUFFERED=1
VOLUME /data
CMD ["python", "app.py"]
