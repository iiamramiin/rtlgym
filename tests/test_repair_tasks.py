# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Repair task definitions keep one source of truth for their grading data."""

import hashlib
from pathlib import Path

import pytest

from rtlgym.task import DEFAULT_TASKS_ROOT, list_tasks, load_task

DESIGN = """top = "arithmetic"
difficulty = "easy"
test_module = "hidden"
sim_timeout_s = 90
tags = ["combinational"]

[formal]
depth = 1
"""
REPAIR = """kind = "repair"
parent = "arithmetic"
starter = "bug_logic.sv"
demo_trajectory = ["bug_logic.sv", "good_logic.sv"]
"""


@pytest.fixture
def tasks(tmp_path):
    design = tmp_path / "arithmetic"
    candidates = design / "candidates"
    candidates.mkdir(parents=True)
    (design / "task.toml").write_text(DESIGN)
    (design / "spec.md").write_text("# Arithmetic")
    (design / "hidden.py").write_text("# Independent reference model\n")
    (design / "ref.sv").write_text("module arithmetic(output logic y);\nassign y = 1'b0;\nendmodule\n")
    (candidates / "bug_logic.sv").write_text(
        "module arithmetic(output logic y);\nassign y = 1'b1;\nendmodule\n"
    )
    (candidates / "good_logic.sv").write_text(
        "module arithmetic(output logic y);\nassign y = '0;\nendmodule\n"
    )
    repair = tmp_path / "repair_arithmetic"
    repair.mkdir()
    (repair / "task.toml").write_text(REPAIR)
    return tmp_path


def test_design_tasks_keep_original_identity_and_fingerprint(tasks):
    design = load_task("arithmetic", tasks)
    former_digest = hashlib.sha256(b"".join(
        f.read_bytes() for f in (design.root / "task.toml", design.ref_path, design.test_path)
    )).hexdigest()[:16]
    assert design.kind == "design" and design.parent_id is None
    assert design.start_path is None and design.start_code is None
    assert design.fingerprint() == former_digest


def test_repair_uses_exact_parent_inputs_and_keeps_own_id(tasks):
    parent = load_task("arithmetic", tasks)
    repair = load_task("repair_arithmetic", tasks)
    assert repair.id == "repair_arithmetic" and repair.root == tasks / repair.id
    assert repair.kind == "repair" and repair.parent_id == parent.id
    assert repair.spec == parent.spec and repair.test_path == parent.test_path
    assert repair.ref_path == parent.ref_path and repair.candidates() == parent.candidates()
    assert repair.formal == parent.formal and repair.sim_timeout_s == parent.sim_timeout_s
    assert (repair.top, repair.difficulty, repair.tags) == (parent.top, parent.difficulty, parent.tags)
    assert repair.start_path == parent.candidates_dir / "bug_logic.sv"
    assert repair.start_code == repair.start_path.read_text()
    assert repair.demo_trajectory == ("bug_logic.sv", "good_logic.sv")


def test_repair_identity_changes_with_manifest_starter_or_parent_data(tasks):
    parent = load_task("arithmetic", tasks)
    repair = load_task("repair_arithmetic", tasks)
    old_repair, old_parent = repair.fingerprint(), parent.fingerprint()
    assert old_repair != old_parent
    repair.start_path.write_text("module arithmetic; /* changed bug */ endmodule\n")
    changed_starter = repair.fingerprint()
    assert changed_starter != old_repair and parent.fingerprint() == old_parent
    manifest = repair.root / "task.toml"
    manifest.write_text(REPAIR + "# Updated task metadata.\n")
    changed_manifest = repair.fingerprint()
    assert changed_manifest != changed_starter and parent.fingerprint() == old_parent
    parent.test_path.write_text("# Different independent reference model\n")
    assert repair.fingerprint() != changed_manifest and parent.fingerprint() != old_parent


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (REPAIR.replace('"repair"', '"nonsense"'), "unknown kind"),
        (REPAIR.replace('parent = "arithmetic"', 'parent = "../arithmetic"'), "separate design parent"),
        (REPAIR.replace('parent = "arithmetic"', 'parent = "repair_arithmetic"'), "separate design parent"),
        (REPAIR.replace('starter = "bug_logic.sv"', 'starter = "../../ref.sv"'), "candidate filename"),
        (REPAIR.replace('starter = "bug_logic.sv"', 'starter = "good_logic.sv"'), "candidate filename"),
        (REPAIR.replace('starter = "bug_logic.sv"', 'starter = "bug_missing.sv"'), "parent candidates"),
        (REPAIR.replace('"good_logic.sv"', '"../ref.sv"'), "demo trajectory"),
        (REPAIR + 'top = "overridden"\n', "unexpected keys"),
        (REPAIR + 'id = "arithmetic"\n', "directory name"),
    ],
)
def test_invalid_manifests_are_rejected(tasks, text, message):
    (tasks / "repair_arithmetic" / "task.toml").write_text(text)
    with pytest.raises(ValueError, match=message):
        load_task("repair_arithmetic", tasks)


def test_missing_and_repair_parents_are_rejected(tasks):
    child = tasks / "child"
    child.mkdir()
    manifest = child / "task.toml"
    manifest.write_text(REPAIR.replace('parent = "arithmetic"', 'parent = "missing"'))
    with pytest.raises(FileNotFoundError, match="no task.toml.*missing"):
        load_task("child", tasks)
    manifest.write_text(REPAIR.replace('parent = "arithmetic"', 'parent = "repair_arithmetic"'))
    parent_manifest = tasks / "repair_arithmetic" / "task.toml"
    parent_manifest.write_text(REPAIR.replace('parent = "arithmetic"', 'parent = "child"'))
    with pytest.raises(ValueError, match="needs a design parent"):
        load_task("child", tasks)


def test_starter_cannot_copy_reference_bytes(tasks):
    parent = load_task("arithmetic", tasks)
    starter = parent.candidates_dir / "bug_logic.sv"
    starter.write_bytes(parent.ref_path.read_bytes())
    with pytest.raises(ValueError, match="starter cannot be the reference"):
        load_task("repair_arithmetic", tasks)


def test_starter_cannot_be_reference_changed_only_in_formatting(tasks):
    parent = load_task("arithmetic", tasks)
    starter = parent.candidates_dir / "bug_logic.sv"
    copy = parent.ref_path.read_text().replace("assign y", "    /* same logic */ assign y")
    starter.write_text("// Different source comment\n\n" + copy)
    with pytest.raises(ValueError, match="starter cannot be the reference"):
        load_task("repair_arithmetic", tasks)


def test_starter_cannot_resolve_outside_candidate_directory(tasks):
    parent = load_task("arithmetic", tasks)
    link = parent.candidates_dir / "bug_link.sv"
    try:
        link.symlink_to(parent.ref_path)
    except OSError:
        pytest.skip("symbolic links unavailable")
    manifest = tasks / "repair_arithmetic" / "task.toml"
    manifest.write_text(REPAIR.replace("bug_logic.sv", "bug_link.sv"))
    with pytest.raises(ValueError, match="parent candidates"):
        load_task("repair_arithmetic", tasks)


def test_repair_catalog_has_eight_distinct_parents_and_difficulty_range():
    repairs = [task for tid in list_tasks() if (task := load_task(tid)).kind == "repair"]
    assert len(repairs) == 8
    assert len({task.parent_id for task in repairs}) == 8
    assert {"easy", "medium", "hard"} <= {task.difficulty for task in repairs}
    assert sum(task.start_path.name.startswith("escape_") for task in repairs) >= 2
    by_parent = {task.parent_id: task for task in repairs}
    for parent in ("noc_router5", "axi4_burst_slave", "cache_controller"):
        assert by_parent[parent].difficulty == "hard"
    for repair in repairs:
        assert repair.root.parent == Path(DEFAULT_TASKS_ROOT)
        assert repair.demo_trajectory[0] == repair.start_path.name
        assert repair.demo_trajectory[-1].startswith("good_")
