#!/bin/bash
set -e

TARGET_UID="${HOST_UID:-1000}"
TARGET_GID="${HOST_GID:-1000}"
TARGET_USER="${HOST_USER:-sondre}"

# Fix ownership on mounted directories
for dir in .openpaper /output; do
    if [ -d "$dir" ]; then
        chown "$TARGET_UID:$TARGET_GID" "$dir"
    fi
done

# Apply skill overrides: copy anything from /overrides/ over the repo
if [ -d /overrides ] && [ "$(ls -A /overrides 2>/dev/null)" ]; then
    echo "[entrypoint] Applying overrides from /overrides/"
    cp -r /overrides/* .
fi

exec gosu "$TARGET_USER" "$@"
