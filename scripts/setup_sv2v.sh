#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

# Install the pinned Linux x86-64 release. Run as the user who runs the grader.
set -euo pipefail
version=v0.0.13
digest=552799a1d76cd177b9b4cc63a3e77823a3d2a6eb4ec006569288abeff28e1ff8
destination=${1:-$HOME/.local/bin}
if [ "$(uname -s)/$(uname -m)" != Linux/x86_64 ]; then
    echo "The pinned sv2v archive is for Linux x86-64. Install sv2v $version for your platform." >&2
    exit 1
fi
scratch=$(mktemp -d)
trap 'rm -f -- "$scratch/sv2v.zip" "$scratch/sv2v"; rmdir -- "$scratch"' EXIT
curl -fsSL --retry 3 -o "$scratch/sv2v.zip" \
    "https://github.com/zachjs/sv2v/releases/download/$version/sv2v-Linux.zip"
printf '%s  %s\n' "$digest" "$scratch/sv2v.zip" | sha256sum -c -
python3 - "$scratch" <<'PY'
import sys
from pathlib import Path
from zipfile import ZipFile

root = Path(sys.argv[1])
with ZipFile(root / "sv2v.zip") as archive:
    (root / "sv2v").write_bytes(archive.read("sv2v-Linux/sv2v"))
PY
install -d "$destination"
install -m 755 "$scratch/sv2v" "$destination/sv2v"
