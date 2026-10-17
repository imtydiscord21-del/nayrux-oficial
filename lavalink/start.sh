#!/bin/sh
set -eu

cookie_file=/tmp/youtube-cookies.txt
if [ -n "${YOUTUBE_COOKIES_B64:-}" ]; then
    printf '%s' "$YOUTUBE_COOKIES_B64" | base64 -d > "$cookie_file"
else
    printf '%s\n' '# Netscape HTTP Cookie File' > "$cookie_file"
fi
chmod 0600 "$cookie_file"

exec java -jar Lavalink.jar
