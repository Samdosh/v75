"""
Silent background launcher for the Deriv Trading Bot.

Runs under pythonw.exe (no console window). Redirects stdout/stderr
to log files and restarts the bot automatically on crash or hang.
"""
import os
import subprocess
import sys
import time

# Hide any console window created by child console processes (python.exe)
CREATE_NO_WINDOW = 0x08000000

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
MAIN_PY = os.path.join(SCRIPT_DIR, "main.py")

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

RUNNER_LOG = os.path.join(LOG_DIR, "runner.log")
STDOUT_LOG = os.path.join(LOG_DIR, "bot_stdout.log")
STDERR_LOG = os.path.join(LOG_DIR, "bot_stderr.log")

# If the bot writes nothing for this long, consider it hung and restart it.
WATCHDOG_TIMEOUT_SECONDS = 300


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(RUNNER_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] [RUNNER] {msg}\n")


def pick_python() -> str:
    # Pure existence check - no subprocess spawning (avoids Task Scheduler hang).
    candidates = [
        os.path.join(sys.prefix, "python.exe"),
        r"C:\Python313\python.exe",
        r"C:\Python311\python.exe",
        "python",
    ]
    for cand in candidates:
        try:
            if os.path.exists(cand) or cand == "python":
                return cand
        except Exception:
            continue
    return sys.executable


def main() -> None:
    log("Launcher started (watchdog enabled).")
    log(f"Log files: {STDOUT_LOG}")

    python_exe = pick_python()
    log(f"Python: {python_exe}")

    max_restarts = 9999
    retry_delay = 15

    for attempt in range(1, max_restarts + 1):
        log(f"Starting bot (restart #{attempt})...")
        stdout_f = open(STDOUT_LOG, "a", encoding="utf-8", errors="replace")
        stderr_f = open(STDERR_LOG, "a", encoding="utf-8", errors="replace")
        proc = None
        code = None
        try:
            proc = subprocess.Popen(
                [python_exe, MAIN_PY],
                cwd=SCRIPT_DIR,
                stdout=stdout_f,
                stderr=stderr_f,
                stdin=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
            # Watchdog baseline: per-spawn, so a stale log file from a previous
            # session cannot cause an immediate false kill.
            last_output = time.time()
            log(f"Watchdog baseline reset (attempt #{attempt}).")
            # Watchdog: restart if the bot writes nothing for too long.
            while True:
                try:
                    code = proc.wait(timeout=15)
                    break
                except subprocess.TimeoutExpired:
                    try:
                        last_write = os.path.getmtime(STDOUT_LOG)
                        if last_write > last_output:
                            last_output = last_write
                    except OSError:
                        pass
                    idle_seconds = time.time() - last_output
                    if idle_seconds > WATCHDOG_TIMEOUT_SECONDS:
                        log(
                            f"Watchdog: no bot output for {int(idle_seconds)}s "
                            f"(>{WATCHDOG_TIMEOUT_SECONDS}s). Restarting."
                        )
                        proc.kill()
                        code = proc.wait()
                        break
        except Exception as e:
            code = -1
            log(f"Failed to launch bot: {e}")
        finally:
            stdout_f.close()
            stderr_f.close()

        log(f"Bot exited (code: {code}). Restarting in {retry_delay}s...")
        time.sleep(retry_delay)


if __name__ == "__main__":
    main()
