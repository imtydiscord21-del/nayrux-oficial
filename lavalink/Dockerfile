FROM denoland/deno:bin-2.9.7 AS deno

FROM ghcr.io/lavalink-devs/lavalink:4.2.2

USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY --from=deno /deno /usr/local/bin/deno

RUN curl --fail --location --silent --show-error \
      https://github.com/yt-dlp/yt-dlp/releases/download/2026.08.19/yt-dlp \
      --output /usr/local/bin/yt-dlp && \
    echo 'a63701f30755cb4d9317950d69703e9d751d490cb1b7059e1bb501a353fe7dcb  /usr/local/bin/yt-dlp' | sha256sum --check && \
    chmod 0755 /usr/local/bin/yt-dlp

COPY application.yml /opt/Lavalink/application.yml
COPY start.sh /opt/Lavalink/start.sh
# Soundy v1.0.3 (MIT); SHA-256: 7981cacf6c40b726387882ec19f3add230750d4f11fd47da4f166be5946fa05d
COPY plugins/soundy-plugin-1.0.3.jar /tmp/soundy-plugin-1.0.3.jar

RUN chmod 0755 /opt/Lavalink/start.sh && chown lavalink:lavalink /opt/Lavalink/start.sh

ENV DENO_DIR=/tmp/deno_cache

USER lavalink

ENTRYPOINT ["/opt/Lavalink/start.sh"]
