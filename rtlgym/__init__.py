"""rtlgym: an RL environment and eval harness for LLM-generated RTL.

An agent receives a natural-language hardware spec, writes SystemVerilog, and
gets a shaped reward from real EDA tools: compile (Icarus Verilog), lint
(Verilator), hidden functional tests (cocotb), and synthesis PPA proxies (Yosys).
"""

from .env import RTLEnv
from .evaluator import EvalResult, evaluate
from .reward import RewardWeights, compute_reward
from .task import Task, list_tasks, load_task

__all__ = [
    "Task",
    "load_task",
    "list_tasks",
    "evaluate",
    "EvalResult",
    "RewardWeights",
    "compute_reward",
    "RTLEnv",
]

__version__ = "0.1.0"
