# The product in one image: the brain, with the panel built in.
# Build from the repo root:  docker build -f brain/Dockerfile -t home-hub/brain .

FROM node:22-alpine AS panel
WORKDIR /app
COPY app/package.json app/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY app/ ./
RUN npm run build

FROM python:3.13-slim
# ffmpeg: sounds dropped into the sounds folder are crossfaded into seamless ten-minute loops before a speaker plays them
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/brain
COPY brain/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY brain/ ./
COPY sounds/ /srv/sounds/
COPY --from=panel /app/dist /srv/app/dist
ARG HUB_VERSION=dev
ARG HUB_COMMIT=
ENV HUB_DATA=/data HUB_PORT=8300 HUB_SOUNDS_LIBRARY=/srv/sounds PYTHONUNBUFFERED=1 HUB_VERSION=$HUB_VERSION HUB_COMMIT=$HUB_COMMIT
VOLUME /data
EXPOSE 8300
CMD ["python", "main.py"]
