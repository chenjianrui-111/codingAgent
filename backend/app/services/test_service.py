import shlex
import subprocess

from app.core.config import settings


class TestService:
    def __init__(self, workspace: str | None = None, test_command: str | None = None):
        self.workspace = workspace or settings.run_workspace
        self.test_command = test_command or settings.run_test_command

    def run_tests(self) -> str:
        cmd = shlex.split(self.test_command)
        try:
            proc = subprocess.run(
                cmd,
                cwd=self.workspace,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError:
            return "test command not found"
        except subprocess.TimeoutExpired:
            return "test command timeout"
        except Exception as exc:  # pragma: no cover
            return f"test runner error: {exc}"

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        merged = "\\n".join([x for x in [stdout, stderr] if x])
        if not merged:
            merged = "no test output"
        return f"exit_code={proc.returncode}\\n{merged}"[:4000]
