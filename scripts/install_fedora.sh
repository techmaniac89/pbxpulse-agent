#!/bin/sh
# Fedora/RHEL-family entry point. The shared installer performs the actual setup.
set -e

if ! command -v dnf >/dev/null 2>&1; then
  echo "This installer requires Fedora, RHEL, Rocky Linux, AlmaLinux, or another dnf-based system."
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer with sudo or as root."
  exit 1
fi

dnf install -y python3 python3-pip python3-devel gcc

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec sh "$SCRIPT_DIR/install_common.sh" "$@"
