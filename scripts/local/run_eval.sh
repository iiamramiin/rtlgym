#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei
#
# Local Ollama experiment: probe (short timing run), smoke (two paired tasks),
# or all (the selected TASKS, with SAMPLES per task). Nothing starts overnight
# runs automatically; select all explicitly.
set -uo pipefail

MODE=${1:-probe}
case "$MODE" in probe|smoke|all) ;; *) echo "usage: $0 probe | smoke | all"; exit 2 ;; esac
HERE=$(cd "$(dirname "$0")" && pwd)
REPO_SRC=${REPO_SRC:-$(cd "$HERE/../.." && pwd)}
RTLGYM_DIR=${RTLGYM_DIR:-$HOME/rtlgym}
VENV=${VENV:-$HOME/venv-rtlgym}
OUT=${OUT:-$REPO_SRC/results/local}
TASKS=${TASKS:-all}
PROBE_TASKS=${PROBE_TASKS:-popcount16}
PROBE_TURNS=${PROBE_TURNS:-3}
SMOKE_TASKS=${SMOKE_TASKS:-popcount16,verify_popcount16}
SAMPLES=${SAMPLES:-1}
TURNS=${TURNS:-3}
PAIRED=${PAIRED:-1}
THINK=${THINK:-default}
TIMEOUT=${TIMEOUT:-3600}
NUM_CTX=${NUM_CTX:-16384}
MAX_TOKENS=${MAX_TOKENS:-8192}
SEED=${SEED:-0}

mkdir -p "$OUT"
LOG="$OUT/run_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1
PY="$VENV/bin/python"
export PATH="$HOME/.local/bin:$PATH"

# Keep existing local results; copy the tracked archive fixtures needed by tests.
if [ -d "$REPO_SRC" ] && [ "$(realpath "$REPO_SRC")" != "$(realpath -m "$RTLGYM_DIR")" ]; then
    mkdir -p "$RTLGYM_DIR"
    rsync -a --delete --exclude results/ --exclude .venv/ --exclude __pycache__/ \
        --exclude .pytest_cache/ --exclude .ruff_cache/ "$REPO_SRC"/ "$RTLGYM_DIR"/ || exit 1
    if git -c safe.directory="$REPO_SRC" -C "$REPO_SRC" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        git -c safe.directory="$REPO_SRC" -C "$REPO_SRC" ls-files -z -- results/ |
            rsync -a --from0 --files-from=- "$REPO_SRC"/ "$RTLGYM_DIR"/ || exit 1
    elif [ -d "$REPO_SRC/results" ]; then
        mkdir -p "$RTLGYM_DIR/results"
        rsync -a --exclude local/ "$REPO_SRC/results"/ "$RTLGYM_DIR/results"/ || exit 1
    fi
fi
cd "$RTLGYM_DIR" || exit 1
echo "rtlgym $(git -c core.fileMode=false describe --always --dirty 2>/dev/null || echo unknown)," \
     "$("$PY" -c 'import cocotb; print("cocotb", cocotb.__version__)')"

# Find the Windows Ollama service without changing networking or starting a server.
HOST=${OLLAMA_URL:-}
if [ -z "$HOST" ]; then
    gw=$(ip route show default 2>/dev/null | awk '{print $3; exit}')
    ns=$(awk '/^nameserver/ {print $2; exit}' /etc/resolv.conf 2>/dev/null)
    for h in http://localhost:11434 ${gw:+http://$gw:11434} ${ns:+http://$ns:11434}; do
        if curl -fsS -m 3 "$h/api/tags" >/dev/null 2>&1; then HOST=$h; break; fi
    done
fi
if [ -z "$HOST" ]; then
    echo "Cannot reach Ollama. Start the local Ollama service, then retry."
    exit 1
fi
echo "Ollama at $HOST"

# The same weights-only RAM guard applies to auto-detected and explicitly named models.
# KV cache, inference workspace, Windows and WSL also need memory; this is a heuristic.
if [ -z "${RAM_GB:-}" ] && command -v powershell.exe >/dev/null 2>&1; then
    RAM_GB=$(powershell.exe -NoProfile -Command \
        "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,3)" \
        2>/dev/null | tr -d '\r')
fi
RAM_GB=${RAM_GB:-$(awk '/MemTotal/ {print $2/1048576}' /proc/meminfo)}
MODELS=$(curl -fsS -m 10 "$HOST/api/tags" |
    RAM_GB="$RAM_GB" REQUESTED_MODELS="${MODELS:-}" "$PY" -c '
import json, os, sys
ram = float(os.environ["RAM_GB"])
if ram <= 0:
    sys.exit("RAM_GB must be positive")
models = {model["name"]: model for model in json.load(sys.stdin)["models"]}
requested = os.environ["REQUESTED_MODELS"].replace(",", " ").split() or sorted(models)
keep = []
for name in dict.fromkeys(requested):
    if name not in models:
        sys.exit(f"Model is not installed: {name}")
    size = models[name].get("size", 0) / 2**30
    if size > 0.75 * ram:
        print(f"Skipping {name}: {size:.2f} GiB weights exceed 75% of {ram:.2f} GiB RAM",
              file=sys.stderr)
    else:
        keep.append(name)
print(" ".join(keep))') || exit 1
echo "Models: $MODELS"
[ -n "$MODELS" ] || { echo "No models fit the RAM guard."; exit 1; }

run() {  # model tasks samples turns out [extra args...]
    local m=$1 tasks=$2 samples=$3 turns=$4 out=$5; shift 5
    "$PY" -m rtlgym run --agent ollama --model "$m" --ollama-host "$HOST" \
        --tasks "$tasks" --samples "$samples" --max-turns "$turns" --workers 1 \
        --think "$THINK" --ollama-timeout "$TIMEOUT" --num-ctx "$NUM_CTX" \
        --max-tokens "$MAX_TOKENS" --seed "$SEED" --out "$out" "$@"
}
slug() { echo "$1" | tr ':/' '__'; }
failures=0

case "$MODE" in
probe)
    mkdir -p "$OUT/probe"
    for m in $MODELS; do
        echo; echo "=== probe: $m ($PROBE_TASKS, 1 sample, up to $PROBE_TURNS turns, full feedback)"
        run "$m" "$PROBE_TASKS" 1 "$PROBE_TURNS" "$OUT/probe/$(slug "$m").json" \
            --feedback full || failures=$((failures + 1))
    done
    task_count=$("$PY" -m rtlgym list --tasks "$TASKS" | awk 'NF {n++} END {print n+0}')
    "$PY" "$HERE/make_table.py" estimate "$OUT/probe" "$task_count" 2 "$SAMPLES" "$TURNS" "$PAIRED" ||
        failures=$((failures + 1))
    ;;
smoke|all)
    selected=$TASKS
    samples=$SAMPLES
    paired=$PAIRED
    if [ "$MODE" = smoke ]; then
        selected=$SMOKE_TASKS
        samples=1
        paired=1
    fi
    for m in $MODELS; do
        base="$OUT/$(slug "$m")"
        if [ "$paired" = 1 ]; then
            if [ -s "${base}__full.json" ] && [ -s "${base}__none.json" ] && [ -s "${base}__paired.json" ]; then
                echo "skip (complete set; use a fresh OUT for new settings): $base"
                continue
            fi
            echo; echo "=== $m, paired arms, $selected, $samples sample(s), $TURNS turns"
            run "$m" "$selected" "$samples" "$TURNS" "$base.json" --paired ||
                failures=$((failures + 1))
        else
            for fb in full none; do
                f="${base}__$fb.json"
                if [ -s "$f" ]; then echo "skip (done; use a fresh OUT for new settings): $f"; continue; fi
                run "$m" "$selected" "$samples" "$TURNS" "$f" --feedback "$fb" ||
                    failures=$((failures + 1))
            done
        fi
    done
    "$PY" "$HERE/make_table.py" table "$OUT" | tee "$OUT/summary.md" ||
        failures=$((failures + 1))
    ;;
esac
echo; echo "Log: $LOG"
[ "$failures" -eq 0 ]
