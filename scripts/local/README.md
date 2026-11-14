# Local-model runs on Windows (WSL + Ollama)

The scripts that produced the local-model results in the main README. They run
rtlgym inside Ubuntu (WSL) and the models in [Ollama](https://ollama.com) on Windows.

| File | Runs as | What it does |
|---|---|---|
| `RUN_ME.bat` | you (double-click) | starts `run_all.ps1` with admin rights |
| `run_all.ps1` | Administrator | installs WSL and Ubuntu 24.04 if needed, sets up networking, runs the two setup scripts, starts Ollama, runs the experiment |
| `setup_system.sh` | root in Ubuntu | installs Icarus Verilog, Verilator, Yosys, and Python tooling |
| `setup_user.sh` | a normal user in Ubuntu | copies the repo (with `.git`) into Linux, creates a venv, runs the test suite |
| `run_eval.sh` | a normal user in Ubuntu | runs the experiment; `probe` mode estimates run time first |
| `make_table.py` | | summary tables and run-time estimates |

## Use

Install Ollama and pull models first (`ollama pull qwen3:14b`). Then double-click
`RUN_ME.bat` and approve the admin prompt. Every step is skipped if already done, so
it is safe to run again; finished result files are kept, so an interrupted run resumes.
Results go to `results/local/` in the repo (ignored by git).

Settings are environment variables, for example in an admin PowerShell:

```powershell
$env:MODELS = "qwen3:14b"; $env:THINK = "off"; $env:SAMPLES = "5"
.\scripts\local\RUN_ME.bat
```

`MODELS`, `SAMPLES` (episodes per task, default 1), `TURNS` (default 3), `PAIRED`
(default 1: one first attempt per episode, branched into the "full" and "none" feedback
arms), `THINK` (`default`/`on`/`off`), `MAX_TOKENS` (default 8192), `TIMEOUT` (seconds
per reply, default 3600), `SEED`. Models larger than about 75% of RAM are skipped.

## Notes

- **Where things go.** Ubuntu's disk goes to `$env:RTLGYM_WSL_DIR`, by default
  `<drive of the repo>:\Program_Files\WSL`. WSL itself is a Windows component and
  always installs on C: (a few hundred MB).
- **Restarts.** Installing WSL for the first time needs a Windows restart. The script
  stops and says so; run it again after the restart.
- **Networking.** On Windows 11 22H2 or later the script adds `networkingMode=mirrored`
  to `%USERPROFILE%\.wslconfig` (merged into an existing file, with a timestamped
  backup; an existing `networkingMode` setting is left alone), so Ubuntu reaches Ollama
  at `localhost:11434`. On older Windows, Ollama must listen on the Windows host address
  (`OLLAMA_HOST=0.0.0.0`) and be allowed through the firewall.
- **Users.** Packages are installed as root; everything else runs as the distro's default
  user, or, if that is root, as a dedicated unprivileged `rtlgym` user with no password.
- **Sleep.** The script keeps Windows awake while its window is open
  (`SetThreadExecutionState`), but closing a laptop's lid can still put it to sleep.
- **Speed.** Without a GPU, replies take minutes: about 1 minute for an 8B model and
  4 to 7 minutes for a 14B model with reasoning off on a 15 GB laptop; Qwen3 with
  reasoning on can take over 30 minutes per reply. Run `bash run_eval.sh probe` first.
