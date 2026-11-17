# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Task definitions.

Each task lives in its own folder under ``tasks/``:

    tasks/<task_id>/
        task.toml          metadata (top module, difficulty, timeouts, demo trajectory,
                           and the [formal] equivalence-check settings)
        spec.md            the only thing the agent sees
        ref.sv             reference RTL (hidden; used for interface and PPA baselines)
        test_<task_id>.py  hidden cocotb testbench with a Python reference model
        candidates/        hand-written correct / buggy / adversarial solutions

A repair task has its own task.toml, with kind="repair", parent (a design task
directory), starter (a bug_* or escape_* filename in the parent's candidates/),
and an optional demo trajectory. It inherits all grading materials and settings.
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

from .checks import same_repair_source

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
    formal: dict = field(default_factory=dict)
    kind: str = "design"
    parent_id: str | None = None
    start_path: Path | None = None
    _grading_root: Path | None = field(default=None, repr=False)
    verify: dict = field(default_factory=dict)
    dut_root: Path | None = field(default=None, repr=False)
    dut_top: str | None = None

    @property
    def verification_root(self) -> Path:
        return self.root

    @property
    def dut_ref_path(self) -> Path:
        return (self.dut_root or self._sources_root) / "ref.sv"

    @property
    def start_code(self) -> str | None:
        return self.start_path.read_text(encoding="utf-8") if self.start_path else None

    @property
    def _sources_root(self) -> Path:
        return self._grading_root if self._grading_root is not None else self.root

    @property
    def has_formal(self) -> bool:
        if self.kind == "verify":
            return True
        return bool(self.formal) and self.formal.get("enabled", True)

    @property
    def ref_path(self) -> Path:
        return self._sources_root / "ref.sv"

    @property
    def test_path(self) -> Path:
        return self._sources_root / f"{self.test_module}.py"

    @property
    def candidates_dir(self) -> Path:
        return self._sources_root / "candidates"

    def candidates(self) -> list[Path]:
        if not self.candidates_dir.is_dir():
            return []
        return sorted(self.candidates_dir.glob("*.sv"))

    def fingerprint(self) -> str:
        """Hash of everything that affects grading, used as part of the cache key."""
        h = hashlib.sha256()
        paths = [self._sources_root / "task.toml", self.ref_path, self.test_path]
        if self.kind == "verify":
            suffixes = {".sv", ".v", ".json", ".toml", ".md"}
            paths = sorted(path for path in self.root.rglob("*") if path.is_file()
                           and path.suffix in suffixes)
            if self.dut_root is not None:
                paths.extend(sorted(path for path in self.dut_root.rglob("*") if path.is_file()
                                    and path.suffix in suffixes))
        if self.start_path is not None:
            paths.extend((self.root / "task.toml", self.start_path))
        for path in paths:
            h.update(path.read_bytes())
        return h.hexdigest()[:16]


def _is_basename(name: object) -> bool:
    return isinstance(name, str) and name not in ("", ".", "..") and not any(
        char in name for char in ("/", "\\", ":", "\0")
    )


def _manifest(task_id: str, tasks_root: Path) -> tuple[Path, dict]:
    if not _is_basename(task_id):
        raise ValueError(f"invalid task ID: {task_id!r}")
    root = tasks_root / task_id
    if root.resolve().parent != tasks_root.resolve():
        raise ValueError(f"task '{task_id}' is outside the tasks root")
    path = root / "task.toml"
    if path.resolve().parent != root.resolve():
        raise ValueError(f"manifest for task '{task_id}' is outside its directory")
    if not path.is_file():
        raise FileNotFoundError(f"no task.toml for task '{task_id}' in {root}")
    return root, tomllib.loads(path.read_text(encoding="utf-8"))


def _design_task(task_id: str, root: Path, meta: dict) -> Task:
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
        formal=dict(meta.get("formal", {})),
    )


def _repair_task(task_id: str, root: Path, meta: dict, tasks_root: Path) -> Task:
    if meta.get("id", task_id) != task_id:
        raise ValueError(f"repair task '{task_id}' must use its directory name as its ID")
    extra = meta.keys() - {"id", "kind", "parent", "starter", "demo_trajectory"}
    if extra:
        raise ValueError(f"repair task '{task_id}' inherits grading; unexpected keys: {sorted(extra)}")
    parent_id = meta.get("parent")
    if not _is_basename(parent_id) or parent_id == task_id:
        raise ValueError(f"repair task '{task_id}' must name a separate design parent")
    parent_root, parent_meta = _manifest(parent_id, tasks_root)
    if parent_meta.get("kind", "design") != "design":
        raise ValueError(f"repair task '{task_id}' needs a design parent, got '{parent_id}'")
    parent = _design_task(parent_id, parent_root, parent_meta)

    starter = meta.get("starter")
    if not _is_basename(starter) or not starter.endswith(".sv") or not starter.startswith(
            ("bug_", "escape_")):
        raise ValueError(f"repair task '{task_id}' needs a bug_* or escape_* candidate filename as starter")
    candidates = parent.candidates_dir
    path = candidates / starter
    if (candidates.resolve() != parent.root.resolve() / "candidates"
            or path.resolve().parent != candidates.resolve() or not path.is_file()):
        raise ValueError(f"repair task '{task_id}' starter '{starter}' is not in the parent candidates")
    starter_bytes, reference_bytes = path.read_bytes(), parent.ref_path.read_bytes()
    if (path.resolve() == parent.ref_path.resolve() or starter_bytes == reference_bytes
            or same_repair_source(starter_bytes.decode("utf-8"), reference_bytes.decode("utf-8"))):
        raise ValueError(f"repair task '{task_id}' starter cannot be the reference design")

    trajectory = meta.get("demo_trajectory", [])
    names = {candidate.name for candidate in parent.candidates()
             if candidate.is_file() and candidate.resolve().parent == candidates.resolve()}
    if not isinstance(trajectory, list) or not all(_is_basename(n) and n in names for n in trajectory):
        raise ValueError(f"repair task '{task_id}' demo trajectory must name parent candidates")

    return replace(parent, id=task_id, root=root, kind="repair", parent_id=parent_id,
                   start_path=path, _grading_root=parent.root, demo_trajectory=tuple(trajectory))


def _verify_task(task_id: str, root: Path, meta: dict, tasks_root: Path) -> Task:
    if meta.get("id", task_id) != task_id:
        raise ValueError(f"verify task '{task_id}' must use its directory name as its ID")
    parent_id = meta.get("parent")
    if not _is_basename(parent_id) or parent_id == task_id:
        raise ValueError(f"verify task '{task_id}' must name a separate design parent")
    parent_root, parent_meta = _manifest(parent_id, tasks_root)
    if parent_meta.get("kind", "design") != "design":
        raise ValueError(f"verify task '{task_id}' needs a design parent, got '{parent_id}'")
    parent = _design_task(parent_id, parent_root, parent_meta)
    verify = meta.get("verification")
    if not isinstance(verify, dict) or not verify:
        raise ValueError(f"verify task '{task_id}' needs [verification] settings")
    manifest = verify.get("manifest", "mutants.json")
    if not _is_basename(manifest) or (root / manifest).resolve().parent != root.resolve():
        raise ValueError(f"verify task '{task_id}' has an invalid mutant manifest")
    if not (root / manifest).is_file():
        raise ValueError(f"verify task '{task_id}' is missing mutant manifest '{manifest}'")
    if meta.get("top", "rtl_checker") != "rtl_checker":
        raise ValueError(f"verify task '{task_id}' must use top 'rtl_checker'")
    if verify.get("dut_top", parent.top) != parent.top:
        raise ValueError(f"verify task '{task_id}' DUT top must match its parent")
    trajectory = meta.get("demo_trajectory", [])
    names = {path.name for path in (root / "candidates").glob("*.sv")}
    if not isinstance(trajectory, list) or not all(_is_basename(n) and n in names for n in trajectory):
        raise ValueError(f"verify task '{task_id}' demo trajectory must name checker candidates")
    return Task(
        id=task_id, root=root, top="rtl_checker", kind="verify", parent_id=parent_id,
        difficulty=meta.get("difficulty", parent.difficulty),
        spec=(root / "spec.md").read_text(encoding="utf-8"),
        test_module="", tags=tuple(meta.get("tags", ("verification",))),
        sim_timeout_s=parent.sim_timeout_s, demo_trajectory=tuple(trajectory),
        formal=dict(verify), verify=dict(verify), dut_root=parent.root, dut_top=parent.top,
    )


def load_task(task_id: str, tasks_root: Path | str = DEFAULT_TASKS_ROOT) -> Task:
    tasks_root = Path(tasks_root)
    root, meta = _manifest(task_id, tasks_root)
    kind = meta.get("kind", "design")
    if kind == "design":
        return _design_task(task_id, root, meta)
    if kind == "repair":
        return _repair_task(task_id, root, meta, tasks_root)
    if kind == "verify":
        return _verify_task(task_id, root, meta, tasks_root)
    raise ValueError(f"task '{task_id}' has unknown kind {kind!r}")


def list_tasks(tasks_root: Path | str = DEFAULT_TASKS_ROOT) -> list[str]:
    root = Path(tasks_root)
    return sorted(p.name for p in root.iterdir() if (p / "task.toml").is_file())
