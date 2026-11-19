#!/bin/sh
set -eu

xvfb_pid=
vnc_pid=
web_pid=
app_pid=
stopping=0
failed=0

request_stop() {
    stopping=1
    if [ -n "$app_pid" ]; then
        kill -TERM "$app_pid" 2>/dev/null || true
    fi
}

cleanup() {
    for pid in $xvfb_pid $vnc_pid $web_pid; do
        kill -TERM "$pid" 2>/dev/null || true
    done

    for attempt in 1 2 3 4 5 6 7 8 9 10; do
        alive=0
        for pid in $xvfb_pid $vnc_pid $web_pid; do
            if kill -0 "$pid" 2>/dev/null; then
                alive=1
            fi
        done
        [ "$alive" -eq 1 ] || break
        sleep 0.1
    done

    for pid in $xvfb_pid $vnc_pid $web_pid; do
        kill -KILL "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    done
}

trap request_stop TERM INT
trap cleanup EXIT

Xvfb :99 -screen 0 1600x900x24 -nolisten tcp &
xvfb_pid=$!

attempt=0

until xdpyinfo -display :99 >/dev/null 2>&1; do
    if [ "$stopping" -eq 1 ]; then
        exit 0
    fi
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

if [ "$stopping" -eq 1 ]; then
    exit 0
fi

echo "Xvfb готов"

x11vnc -display :99 -localhost -nopw -forever -shared -rfbport 5900 &
vnc_pid=$!

websockify --web=/usr/share/novnc 6080 localhost:5900 &
web_pid=$!

python main.py &
app_pid=$!
if [ "$stopping" -eq 1 ]; then
    request_stop
fi

while kill -0 "$app_pid" 2>/dev/null; do
    if [ "$stopping" -eq 0 ]; then
        if ! kill -0 "$xvfb_pid" 2>/dev/null || ! kill -0 "$vnc_pid" 2>/dev/null || ! kill -0 "$web_pid" 2>/dev/null; then
            echo "Завершился процесс графического окружения" >&2
            failed=1
            request_stop
        fi
    fi
    sleep 0.2
done

status=0
wait "$app_pid" || status=$?
if [ "$failed" -eq 1 ]; then
    exit 1
fi
if [ "$stopping" -eq 1 ] && [ "$status" -eq 143 ]; then
    # Python may receive SIGTERM before entering its application code.
    exit 0
fi
exit "$status"
