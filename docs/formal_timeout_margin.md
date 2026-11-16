# Measuring formal timeout headroom

Use the configured local toolchain and run from the repository root. Keep four
workers to match the archived November 14, 2026 experiment. Start with an
uncached baseline so every reference has a fresh formal-stage time.

```bash
python -m rtlgym baselines --workers 4 --no-cache --out /tmp/rtlgym-formal-baselines.json
python - /tmp/rtlgym-formal-baselines.json <<'PY'
import inspect
import json
import math
import sys
from pathlib import Path

from rtlgym.formal import check_equivalence
from rtlgym.task import list_tasks, load_task

rows = json.loads(Path(sys.argv[1]).read_text())
default_timeout = inspect.signature(check_equivalence).parameters["timeout_s"].default
failures = 0
print(f"{'task':24} {'proof (s)':>10} {'limit (s)':>10} {'margin':>8} result")
for task_id in list_tasks():
    task = load_task(task_id)
    if not task.has_formal:
        print(f"{task.id:24} {'-':>10} {'-':>10} {'-':>8} disabled")
        continue
    refs = [row for row in rows if (row["task"], row["candidate"]) == (task.id, "ref.sv")]
    if len(refs) != 1:
        print(f"{task.id:24} {'-':>10} {'-':>10} {'-':>8} expected one reference result")
        failures += 1
        continue
    ref = refs[0]
    elapsed = ref["timings_s"].get("formal")
    if ref["formal"] != "pass" or elapsed is None or not math.isfinite(elapsed) or elapsed <= 0:
        print(f"{task.id:24} {'-':>10} {'-':>10} {'-':>8} missing or nonpassing proof timing")
        failures += 1
        continue
    timeout = float(task.formal.get("timeout_s", default_timeout))
    margin = timeout / elapsed
    passed = margin >= 4
    print(f"{task.id:24} {elapsed:10.3f} {timeout:10.1f} {margin:7.2f}x "
          f"{'pass' if passed else 'below 4x'}")
    failures += int(not passed)
raise SystemExit(bool(failures))
PY
```

The check uses the configured SAT timeout and the observed formal-stage wall
time. It uses no outer process grace period. A passing margin measures the
reference on that run. Also inspect formal outcomes for the known-good
alternates, which may have much more expensive proofs.
