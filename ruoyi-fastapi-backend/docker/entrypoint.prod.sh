#!/usr/bin/env sh
set -eu

if [ "$(id -u)" = "0" ]; then
    for directory in \
        /app/vf_admin/gen_path \
        /app/vf_admin/upload_path \
        /app/vf_admin/private_upload_path \
        /app/vf_admin/file_trash_path \
        /app/vf_admin/file_reconcile_quarantine_path \
        /app/vf_admin/download_path \
        /app/logs \
        /app/caches
    do
        mkdir -p "$directory"
        chown app:app "$directory"
    done
    chown app:app /app/vf_admin
    exec gosu app "$@"
fi

exec "$@"
