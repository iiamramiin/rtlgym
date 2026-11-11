"""Task definitions.

Each task lives in its own folder under ``tasks/``:

    tasks/<task_id>/
        task.toml          metadata (top module, difficulty, timeouts, demo trajectory)
        spec.md            the only thing the agent sees
        ref.sv             reference RTL (hidden; used for interface and PPA baselines)
        test_<task_id>.py  hidden cocotb testbench with a Python reference model
        candidates/        hand-written correct / buggy / adversarial solutions
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TASKS_ROOT = Path(__file__).resolve().parent.parent / "tasks"


@dataclass(frozen=True)
class Task:
    id: str
    root: Path
    top: str
    difficulty: str
    spec: str
    test_module: str
    sim_timeout_s: float = 60.0
    tags: tuple[str, ...] = ()
    demo_trajectory: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ref_path(self) -> Path:
        return self.root / "ref.sv"

    @property
    def test_path(self) -> Path:
        return self.root / f"{self.test_module}.py"

    @property
    def candidates_dir(self) -> Path:
        return self.root / "candidates"

    def candidates(self) -> list[Path]:
        if not self.candidates_dir.is_dir():
            return []
        return sorted(self.candidates_dir.glob("*.sv"))

    def fingerprint(self) -> str:
        """Hash of everything that affects grading, used as part of the cache key."""
        h = hashlib.sha256()
        for p in (self.root / "task.toml", self.ref_path, self.test_path):
            h.update(p.read_bytes())
        return h.hexdigest()[:16]


def load_task(task_id: str, tasks_root: Path | str = DEFAULT_TASKS_ROOT) -> Task:
    root = Path(tasks_root) / task_id
    meta_path = root / "task.toml"
    if not meta_path.is_file():
        raise FileNotFoundError(f"no task.toml for task '{task_id}' in {root}")
    meta = tomllib.loads(meta_path.read_text())
    spec = (root / "spec.md").read_text()
    return Task(
        id=meta.get("id", task_id),
        root=root,
        top=meta["top"],
        difficulty=meta.get("difficulty", "medium"),
        spec=spec,
        test_module=meta.get("test_module", f"test_{task_id}"),
        sim_timeout_s=float(meta.get("sim_timeout_s", 60)),
        tags=tuple(meta.get("tags", [])),
        demo_trajectory=tuple(meta.get("demo_trajectory", [])),
    )


def list_tasks(tasks_root: Path | str = DEFAULT_TASKS_ROOT) -> list[str]:
    root = Path(tasks_root)
    return sorted(p.name for p in root.iterdir() if (p / "task.toml").is_file())
