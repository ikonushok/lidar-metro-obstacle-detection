#!/bin/sh
set -eu

cd /app

for archive in for_hackathon new_data cloud_with_fake_obj; do
    if [ ! -f "dataset/for_hackathon/$archive" ]; then
        if [ ! -d dataset/raw ]; then
            echo "Missing dataset/for_hackathon/$archive. Put the three supplier archives in dataset/raw/ and rerun docker compose up --build." >&2
            exit 1
        fi
        python3 /app/scripts/prepare_hackathon_datasets.py \
            --raw-dir /app/dataset/raw \
            --catalog-dir /app/dataset/for_hackathon
        break
    fi
done

exec python3 -u /app/scripts/serve_stage_2_cpu_catalog.py \
    --root /app \
    --rail-selection-method development_candidate \
    --rail-forward-min-m 2 \
    --forward-extension-method tangent \
    --noise-filter-mode baseline_v3
