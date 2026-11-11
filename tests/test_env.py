import pytest

from rtlgym import RTLEnv
from rtlgym.agents import ReplayAgent

pytestmark = pytest.mark.needs_tools


def rollout(env, agent, task_id):
    obs, _ = env.reset(task_id=task_id)
    agent.begin_episode(obs)
    rewards = []
    while True:
        obs, r, term, trunc, info = env.step(agent.act(obs))
        rewards.append(r)
        if term or trunc:
            return obs, rewards, term, trunc, info


def test_reset_observation_has_spec_only():
    env = RTLEnv()
    obs, info = env.reset(task_id="alu8")
    assert obs["task_id"] == "alu8" and obs["top"] == "alu8"
    assert "## Interface" in obs["spec"] and obs["feedback"] == "" and obs["turns_left"] == 3


def test_reset_random_task_is_seeded():
    a = RTLEnv().reset(seed=3)[0]["task_id"]
    b = RTLEnv().reset(seed=3)[0]["task_id"]
    assert a == b


def test_step_before_reset_raises():
    with pytest.raises(RuntimeError):
        RTLEnv().step("module x; endmodule")


def test_improvement_rewards_sum_to_best_score():
    env = RTLEnv(max_turns=3)
    _, rewards, term, _, info = rollout(env, ReplayAgent(), "uart_tx")
    assert term
    assert sum(rewards) == pytest.approx(info["best_score"], abs=1e-3)
    assert all(r >= 0 for r in rewards)


def test_score_mode_and_feedback_content():
    env = RTLEnv(max_turns=1, reward_mode="score")
    obs, rewards, term, trunc, info = rollout(env, ReplayAgent(), "fifo_sync")
    assert trunc and not term
    assert rewards[0] == info["score"]
    assert "Hidden tests:" in obs["feedback"] and "FAIL" in obs["feedback"]


def test_summary_feedback_hides_test_details():
    env = RTLEnv(max_turns=1, feedback="summary")
    obs, *_ = rollout(env, ReplayAgent(), "fifo_sync")
    assert "Hidden tests:" in obs["feedback"] and "FAIL" not in obs["feedback"]


def test_compile_error_feedback():
    env = RTLEnv(max_turns=2)
    env.reset(task_id="popcount16")
    obs, r, term, trunc, info = env.step("```verilog\nmodule popcount16(input x; endmodule\n```")
    assert r == 0.0 and not term and not trunc
    assert "Compilation failed" in obs["feedback"]


def test_rejected_hack_feedback():
    env = RTLEnv()
    env.reset(task_id="popcount16")
    obs, r, *_ = env.step("module popcount16(input logic [15:0] x, output logic [4:0] count);"
                          " initial $finish; endmodule")
    assert r == 0.0 and "Rejected" in obs["feedback"]


def test_test_escape_keeps_episode_open_with_counterexample():
    env = RTLEnv(max_turns=2)
    env.reset(task_id="popcount16")
    code = (env.tasks_root / "popcount16" / "candidates" / "escape_rare_input.sv").read_text()
    obs, r, term, trunc, info = env.step(code)
    assert not term and not trunc and not info["solved"]
    assert "every hidden test passes, but the formal check" in obs["feedback"]
    assert "x=0xbeef" in obs["feedback"]


def test_summary_feedback_hides_counterexample():
    env = RTLEnv(max_turns=1, feedback="summary")
    env.reset(task_id="popcount16")
    code = (env.tasks_root / "popcount16" / "candidates" / "escape_rare_input.sv").read_text()
    obs, *_ = env.step(code)
    assert "Formal:" in obs["feedback"] and "0xbeef" not in obs["feedback"]


def test_formal_can_be_disabled_for_ablations():
    env = RTLEnv(max_turns=2, use_formal=False)
    env.reset(task_id="popcount16")
    code = (env.tasks_root / "popcount16" / "candidates" / "escape_rare_input.sv").read_text()
    obs, r, term, trunc, info = env.step(code)
    assert info["eval"].formal_status == "disabled"
    assert term and info["solved"]          # without formal, the escape looks solved
