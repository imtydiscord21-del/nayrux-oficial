FROM ghcr.io/lavalink-devs/lavalink:4.2.2

USER root

COPY application.yml /opt/Lavalink/application.yml
COPY start.sh /opt/Lavalink/start.sh
# Soundy v1.0.3 (MIT); SHA-256: 7981cacf6c40b726387882ec19f3add230750d4f11fd47da4f166be5946fa05d
COPY plugins/soundy-plugin-1.0.3.jar /tmp/soundy-plugin-1.0.3.jar

RUN chmod 0755 /opt/Lavalink/start.sh && chown lavalink:lavalink /opt/Lavalink/start.sh

ENV DENO_DIR=/tmp/deno_cache

USER lavalink

ENTRYPOINT ["/opt/Lavalink/start.sh"]
