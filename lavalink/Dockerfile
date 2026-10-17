FROM gradle:8.10-jdk17 AS youtube-plugin-build

ARG YOUTUBE_SOURCE_COMMIT=1ddb648257d5b547aa1e2dfb8104edf6cb1089be
WORKDIR /src/youtube-source
RUN git init . \
    && git remote add origin https://github.com/ashton045/youtube-source.git \
    && git fetch --depth 1 origin "$YOUTUBE_SOURCE_COMMIT" \
    && git checkout --detach FETCH_HEAD
RUN ./gradlew :plugin:shadowJar --no-daemon

FROM ghcr.io/lavalink-devs/lavalink:4.2.2

USER root

COPY application.yml /opt/Lavalink/application.yml
COPY start.sh /opt/Lavalink/start.sh
COPY --from=youtube-plugin-build /src/youtube-source/plugin/build/libs/youtube-plugin-1ddb648257d5b547aa1e2dfb8104edf6cb1089be.jar /tmp/youtube-plugin.jar
# Soundy v1.0.3 (MIT); SHA-256: 7981cacf6c40b726387882ec19f3add230750d4f11fd47da4f166be5946fa05d
COPY plugins/soundy-plugin-1.0.3.jar /tmp/soundy-plugin-1.0.3.jar

RUN chmod 0755 /opt/Lavalink/start.sh && chown lavalink:lavalink /opt/Lavalink/start.sh

ENV DENO_DIR=/tmp/deno_cache

USER lavalink

ENTRYPOINT ["/opt/Lavalink/start.sh"]
