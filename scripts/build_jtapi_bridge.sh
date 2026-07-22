#!/bin/sh
set -e

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
OUTPUT_DIR="$ROOT_DIR/jtapi_bridge/classes"

if ! command -v javac >/dev/null 2>&1; then
  echo "javac is required to rebuild the JTAPI bridge." >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
javac -source 8 -target 8 -d "$OUTPUT_DIR" \
  "$ROOT_DIR/jtapi_bridge/PBXSenseJtapiBridge.java"
