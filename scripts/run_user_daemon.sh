#!/bin/sh
set -eu

# User-space restart wrapper for the loopback Pocket Rocket service.  It makes
# no system changes and never installs itself.  The model process retains its
# own process-tree 14.5 GiB RSS guard.
project_root=${POCKET_ROCKET_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
service_binary=${POCKET_ROCKET_BINARY:-$project_root/.venv/bin/neuro-inverse}
service_port=${POCKET_ROCKET_PORT:-8000}
log_root=$project_root/var/log

case $service_port in
    ''|*[!0-9]*) echo "POCKET_ROCKET_PORT must be an integer" >&2; exit 2 ;;
esac
if [ "$service_port" -le 1024 ] || [ "$service_port" -gt 65535 ]; then
    echo "POCKET_ROCKET_PORT must be between 1025 and 65535" >&2
    exit 2
fi
if [ ! -x "$service_binary" ]; then
    echo "Pocket Rocket service executable not found: $service_binary" >&2
    exit 2
fi
mkdir -p -- "$log_root"

stopping=0
child_pid=
stop_service() {
    stopping=1
    if [ -n "$child_pid" ]; then
        kill -TERM "$child_pid" 2>/dev/null || true
        wait "$child_pid" 2>/dev/null || true
    fi
}
trap stop_service INT TERM HUP

sequence=0
while [ "$stopping" -eq 0 ]; do
    sequence=$((sequence + 1))
    run_log=$log_root/service-$(date -u +%Y%m%dT%H%M%SZ)-$$-$sequence.log
    printf 'launch=%s serve --port %s\n' "$service_binary" "$service_port" >"$run_log"
    "$service_binary" serve --port "$service_port" >>"$run_log" 2>&1 &
    child_pid=$!
    set +e
    wait "$child_pid"
    exit_status=$?
    set -e
    child_pid=
    printf 'exit_status=%s\n' "$exit_status" >>"$run_log"
    [ "$stopping" -ne 0 ] && break
    sleep 2
done
