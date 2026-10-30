#!/bin/bash
set -e
cd "$(dirname "$0")"
TARGET="${1:-127.0.0.1}"
PORT="${2:-80}"
THREADS="${3:-200}"
DUR="${4:-60}"
METHODS="${5:-http}"
./stress.py "$TARGET" -p "$PORT" -t "$THREADS" -d "$DUR" -m $METHODS --confirm
