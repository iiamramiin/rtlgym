#!/usr/bin/env bash
# Runs the feedback experiment for one or more models and writes a Markdown summary.
# Used by .github/workflows/eval.yml; runs the same way locally (AGENT=replay needs
# no API key).
#
# Settings (environment variables):
#   MODELS="claude-sonnet-5-5"   comma-separated model IDs
#   TASKS=all                    comma-separated task IDs, or "all"
#   SAMPLES=5 MAX_TURNS=3        episodes per task, attempts per episode
#   PAIRED=true                  true: one first attempt branched into the "full" and
#                                "none" arms (--paired); false: run each FEEDBACK arm
#   FEEDBACK="full,none"         arms to run when PAIRED=false
#   EFFORT=                      low|medium|high|xhigh|max, or empty/"default"
#   WORKERS=4                    episodes graded in parallel
#   AGENT=claude                 or "replay" (offline, for testing this script)
#   OUT=results                  output folder
#   PYTHON=python
# Exits non-zero if any run failed completely; the summary is written regardless.
set -uo pipefail

MODELS=${MODELS:-claude-sonnet-5-5}
TASKS=${TASKS:-all}
SAMPLES=${SAMPLES:-5}
MAX_TURNS=${MAX_TURNS:-3}
PAIRED=${PAIRED:-true}
FEEDBACK=${FEEDBACK:-full,none}
EFFORT=${EFFORT:-}
WORKERS=${WORKERS:-4}
AGENT=${AGENT:-claude}
OUT=${OUT:-results}
PYTHON=${PYTHON:-python}
HERE=$(cd "$(dirname "$0")" && pwd)
[ "$EFFORT" = default ] && EFFORT=

mkdir -p "$OUT"
[ "$AGENT" = replay ] && MODELS=replay            # the replay agent has no model
models=$(echo "$MODELS" | tr ',' ' ')
arms=$(echo "$FEEDBACK" | tr ',' ' ')
if [ "$TASKS" = all ]; then
    n_tasks=$("$PYTHON" -m rtlgym list | grep -c .)
else
    n_tasks=$(echo "$TASKS" | tr ',' '\n' | grep -c .)
fi
n_models=$(echo "$models" | wc -w)
n_arms=$(echo "$arms" | wc -w)
calls=$("$PYTHON" "$HERE/summary.py" plan "$n_models" "$n_tasks" "$SAMPLES" "$MAX_TURNS" \
        "$PAIRED" "$n_arms")
echo "Plan: $n_models model(s) x $n_tasks task(s) x $SAMPLES episode(s), up to $MAX_TURNS" \
     "attempts, paired=$PAIRED -> at most $calls API calls (fewer when attempts are" \
     "accepted early)."

failed=0
run() {  # model out [extra args...]
    local m=$1 out=$2; shift 2
    local args=(--agent "$AGENT" --tasks "$TASKS" --samples "$SAMPLES"
                --max-turns "$MAX_TURNS" --workers "$WORKERS" --out "$out" "$@")
    [ "$AGENT" != replay ] && args+=(--model "$m")
    [ -n "$EFFORT" ] && args+=(--effort "$EFFORT")
    echo; echo "=== $m $* [$(date -u +%H:%M) UTC]"
    "$PYTHON" -m rtlgym run "${args[@]}" || failed=1
}
for m in $models; do
    if [ "$PAIRED" = true ]; then
        run "$m" "$OUT/$m.json" --paired          # writes $m__full, __none, __paired
    else
        for fb in $arms; do run "$m" "$OUT/${m}__$fb.json" --feedback "$fb"; done
    fi
done

shopt -s nullglob
arm_files=()
for f in "$OUT"/*.json; do [[ $f == *__paired.json ]] || arm_files+=("$f"); done
{
    echo "## rtlgym eval"
    echo
    echo "Models: $MODELS. Tasks: $TASKS. $SAMPLES episode(s) per task, up to $MAX_TURNS" \
         "attempts, paired=$PAIRED, effort=${EFFORT:-model default}, workers=$WORKERS." \
         "Planned: at most $calls API calls."
    echo
    if [ ${#arm_files[@]} -gt 0 ]; then
        "$PYTHON" -m rtlgym report "${arm_files[@]}"
    else
        echo "No result files were written."
    fi
    echo
    "$PYTHON" "$HERE/summary.py" report "$OUT"
} > "$OUT/summary.md"
cat "$OUT/summary.md"
[ -n "${GITHUB_STEP_SUMMARY:-}" ] && cat "$OUT/summary.md" >> "$GITHUB_STEP_SUMMARY"
exit $failed
