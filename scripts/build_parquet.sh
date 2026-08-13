#!/bin/sh
set -eu
bash scripts/build_public_config.sh
./node_modules/.bin/vite build --config parquet/vite.config.ts
