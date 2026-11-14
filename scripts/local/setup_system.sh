#!/usr/bin/env bash
# System packages for rtlgym inside Ubuntu (WSL). Run as root, once.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
need=()
for pkg in iverilog verilator yosys python3-venv python3-pip make g++ curl git rsync; do
    dpkg -s "$pkg" >/dev/null 2>&1 || need+=("$pkg")
done
if [ ${#need[@]} -gt 0 ]; then
    apt-get update
    apt-get install -y --no-install-recommends "${need[@]}"
fi
iverilog -V 2>/dev/null | head -1; verilator --version; yosys -V
