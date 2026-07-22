#!/bin/sh
# Debian/Ubuntu-family entry point. Keep this file in Unix LF format.
set -e

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer requires Debian, Ubuntu, Raspberry Pi OS, or another apt-based system."
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer with sudo or as root."
  exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec sh "$SCRIPT_DIR/install_common.sh" "$@"
