#!/usr/bin/env bash
# Runs the rtlgym feedback experiment on local Ollama models (inside WSL or Linux).
#
#   bash run_eval.sh probe     # one task per model: measures speed, estimates a full run
#   bash run_eval.sh all       # every task, both feedback arms, every model that fits
#
# Settings (environment variables):
#   REPO_SRC     the repo to run (default: the repo this script is in)
#   OUT          results folder (default: $REPO_SRC/results/local)
#   MODELS       e.g. "llama3.1:8b qwen3:14b" (default: every installed model that
#                fits in RAM)
#   SAMPLES=1 TURNS=3          episodes per task, attempts per episode
#   PAIRED=1     1: one first attempt per episode, branched into the "full" and "none"
#                arms (a paired comparison); 0: two independent runs
#   THINK=default|on|off       reasoning mode for models that have one (e.g. Qwen3)
#   MAX_TOKENS   reply cap per call, reasoning included (rtlgym default: 8192)
#   TIMEOUT=3600 seconds to wait for one reply
#   SEED         base sampling seed (each episode uses SEED + its index)
# Finished result files are skipped, so an interrupted run can be restarted.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO_SRC=${REPO_SRC:-$(cd "$HERE/../.." && pwd)}
RTLGYM_DIR=${RTLGYM_DIR:-$HOME/rtlgym}
VENV=${VENV:-$HOME/venv-rtlgym}
OUT=${OUT:-$REPO_SRC/results/local}
SAMPLES=${SAMPLES:-1}
TURNS=${TURNS:-3}
PAIRED=${PAIRED:-1}
THINK=${THINK:-default}
TIMEOUT=${TIMEOUT:-3600}
NUM_CTX=${NUM_CTX:-16384}
MODE=${1:-probe}

mkdir -p "$OUT"
LOG="$OUT/run_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1
PY="$VENV/bin/python"

# Run the latest code from the Windows side (with .git, so results record the commit).
if [ -d "$REPO_SRC" ] && [ "$(realpath "$REPO_SRC")" != "$(realpath -m "$RTLGYM_DIR")" ]; then
    rsync -a --delete --exclude results/ "$REPO_SRC"/ "$RTLGYM_DIR"/
fi
cd "$RTLGYM_DIR" || exit 1
echo "rtlgym $(git -c core.fileMode=false describe --always --dirty 2>/dev/null || echo unknown)," \
     "$("$PY" -c 'import cocotb; print("cocotb", cocotb.__version__)')"

# Find Ollama: localhost (mirrored networking), else the Windows host address.
HOST=${OLLAMA_URL:-}
if [ -z "$HOST" ]; then
    gw=$(ip route show default 2>/dev/null | awk '{print $3; exit}')
    ns=$(awk '/^nameserver/ {print $2; exit}' /etc/resolv.conf 2>/dev/null)
    for h in http://localhost:11434 ${gw:+http://$gw:11434} ${ns:+http://$ns:11434}; do
        if curl -s -m 3 "$h/api/tags" >/dev/null; then HOST=$h; break; fi
    done
fi
if [ -z "$HOST" ]; then
    echo "Cannot reach Ollama. Start the Ollama app on Windows (or run 'ollama serve') and retry."
    exit 1
fi
echo "Ollama at $HOST"

if [ -z "${MODELS:-}" ]; then
    # Skip models too big for this computer's RAM (they would swap for hours, not run).
    if [ -z "${RAM_GB:-}" ] && command -v powershell.exe >/dev/null 2>&1; then
        RAM_GB=$(powershell.exe -NoProfile -Command \
            "[math]::Floor((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB)" \
            2>/dev/null | tr -dc '0-9')
    fi
    RAM_GB=${RAM_GB:-$(awk '/MemTotal/ {print int($2/1048576)}' /proc/meminfo)}
    MODELS=$(curl -s "$HOST/api/tags" | RAM_GB=$RAM_GB "$PY" -c '
import json, os, sys
ram_gb = float(os.environ["RAM_GB"] or 0)
keep = []
for m in sorted(json.load(sys.stdin)["models"], key=lambda m: m["name"]):
    name, size_gb = m["name"], m.get("size", 0) / 2**30
    if ram_gb and size_gb > 0.75 * ram_gb:
        print(f"Skipping {name}: {size_gb:.1f} GB is too big for {ram_gb:.0f} GB of RAM",
              file=sys.stderr)
    else:
        keep.append(name)
print(" ".join(keep))')
fi
echo "Models: $MODELS"
[ -n "$MODELS" ] || { echo "No models to run."; exit 1; }

run() {  # model tasks samples turns out [extra args...]
    local m=$1 tasks=$2 samples=$3 turns=$4 out=$5; shift 5
    local extra=(--think "$THINK" --ollama-timeout "$TIMEOUT" --num-ctx "$NUM_CTX")
    [ -n "${MAX_TOKENS:-}" ] && extra+=(--max-tokens "$MAX_TOKENS")
    [ -n "${SEED:-}" ] && extra+=(--seed "$SEED")
    "$PY" -m rtlgym run --agent ollama --model "$m" --ollama-host "$HOST" \
        --tasks "$tasks" --samples "$samples" --max-turns "$turns" --workers 1 \
        --out "$out" "${extra[@]}" "$@"
}

slug() { echo "$1" | tr ':/' '__'; }

case "$MODE" in
probe)
    mkdir -p "$OUT/probe"
    for m in $MODELS; do
        echo; echo "=== probe: $m (popcount16, 1 episode, up to 3 turns, full feedback)"
        run "$m" popcount16 1 3 "$OUT/probe/$(slug "$m").json" --feedback full
    done
    "$PY" "$HERE/make_table.py" estimate "$OUT/probe" 8 2 "$SAMPLES" "$TURNS"
    ;;
all)
    for m in $MODELS; do
        base="$OUT/$(slug "$m")"
        if [ "$PAIRED" = 1 ]; then
            if [ -s "${base}__paired.json" ]; then echo "skip (done): ${base}__paired.json"; continue; fi
            echo; echo "=== $m, paired arms (full / none), $SAMPLES sample(s) per task, $TURNS turns  [$(date +%H:%M)]"
            run "$m" all "$SAMPLES" "$TURNS" "$base.json" --paired
        else
            for fb in full none; do
                f="${base}__$fb.json"
                if [ -s "$f" ]; then echo "skip (done): $f"; continue; fi
                echo; echo "=== $m, feedback $fb, $SAMPLES sample(s) per task, $TURNS turns  [$(date +%H:%M)]"
                run "$m" all "$SAMPLES" "$TURNS" "$f" --feedback "$fb"
            done
        fi
    done
    "$PY" "$HERE/make_table.py" table "$OUT" | tee "$OUT/summary.md"
    ;;
*)
    echo "usage: $0 probe | all"; exit 2 ;;
esac
echo; echo "Log: $LOG"
