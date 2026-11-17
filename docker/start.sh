#!/bin/sh
set -eu

Xvfb :99 -screen 0 1600x900x24 -nolisten tcp &
xvfb_pid=$!

attempt=0

until xdpyinfo -display :99 >/dev/null 2>&1; do
    if ! kill -0 "$xvfb_pid" 2>/dev/null; then
        echo "Xvfb завершился с ошибкой" >&2
        exit 1
    fi

    attempt=$((attempt + 1))

    if [ "$attempt" -ge 30 ]; then
        echo "Xvfb не готов" >&2
        exit 1
    fi

    sleep 0.2
done

echo "Xvfb готов"

x11vnc -display :99 -localhost -nopw -forever -shared -rfbport 5900 &

websockify --web=/usr/share/novnc 6080 localhost:5900 &

exec python main.py
