#!/usr/bin/env bash
# Entry point of infra/app.Dockerfile: the backend and nginx in one container. The container exits as soon as either
# process does, so Azure restarts the whole replica instead of serving a site without its API.
set -euo pipefail

mkdir -p /tmp/nginx
# One worker only: jobs and their progress live in this process's memory.
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-server-header &
nginx -g 'daemon off;' &

trap 'kill -TERM $(jobs -p) 2>/dev/null' TERM INT
wait -n
status=$?
# shellcheck disable=SC2046 # one argument per remaining job
kill -TERM $(jobs -p) 2>/dev/null || true
exit "$status"
