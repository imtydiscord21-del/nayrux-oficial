FROM ghcr.io/lavalink-devs/lavalink:4.2.2

COPY application.yml /opt/Lavalink/application.yml
# Soundy v1.0.3 (MIT); SHA-256: 7981cacf6c40b726387882ec19f3add230750d4f11fd47da4f166be5946fa05d
COPY plugins/soundy-plugin-1.0.3.jar /opt/Lavalink/plugins/soundy-plugin-1.0.3.jar
# Lavalink runs as UID/GID 322 and downloads configured plugins at startup.
RUN chown 322:322 /opt/Lavalink/plugins
