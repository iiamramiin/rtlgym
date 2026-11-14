#!/usr/bin/env bash
# rtlgym and its Python environment, as a normal user. Safe to rerun.
#   REPO_SRC    the repo on the Windows side (e.g. /mnt/e/.../rtlgym)
set -euo pipefail
REPO_SRC=${REPO_SRC:?set REPO_SRC to the repo path}
RTLGYM_DIR=${RTLGYM_DIR:-$HOME/rtlgym}
VENV=${VENV:-$HOME/venv-rtlgym}

echo "== Copying $REPO_SRC to $RTLGYM_DIR (with .git, so results record the commit)"
mkdir -p "$RTLGYM_DIR"
rsync -a --delete --exclude results/ "$REPO_SRC"/ "$RTLGYM_DIR"/
git -C "$RTLGYM_DIR" config core.fileMode false 2>/dev/null || true

echo "== Python environment in $VENV"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -e "$RTLGYM_DIR[dev]"
"$VENV/bin/python" -c "import cocotb; print('cocotb', cocotb.__version__)"

echo "== Test suite"
cd "$RTLGYM_DIR" && "$VENV/bin/python" -m pytest -q -n auto
