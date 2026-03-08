"""Stateful Python execution kernel for data analysis.

Provides a per-session Python execution environment where variables,
imports, and DataFrames persist across multiple code executions --
similar to a Jupyter kernel but without the Jupyter dependency.

Uses a subprocess running a REPL loop communicating via stdin/stdout
with JSON-encoded messages.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import signal
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

KERNEL_TIMEOUT = 120  # seconds per execution
MAX_OUTPUT_SIZE = 64_000  # characters
MAX_FIGURE_SIZE = 2 * 1024 * 1024  # 2 MB per figure

# The kernel REPL script that runs in a subprocess
KERNEL_SCRIPT = r'''
import sys, json, io, os, traceback, contextlib, base64

# Pre-import common data libraries
try:
    import pandas as pd
    import numpy as np
except ImportError:
    pass

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

# Persistent namespace for user code
_ns = {"__builtins__": __builtins__}

# Figure output directory (passed as env var)
_fig_dir = os.environ.get("KERNEL_FIG_DIR", "/tmp/figures")
os.makedirs(_fig_dir, exist_ok=True)

def _capture_figures():
    """Capture all open matplotlib figures as base64 PNG."""
    if plt is None:
        return []
    figs = []
    for fig_num in plt.get_fignums():
        fig = plt.figure(fig_num)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
        buf.seek(0)
        data = base64.b64encode(buf.read()).decode("utf-8")
        figs.append({"figure_num": fig_num, "data_base64": data, "format": "png"})
        buf.close()
    plt.close("all")
    return figs

while True:
    try:
        line = sys.stdin.readline()
        if not line:
            break
        msg = json.loads(line)
        code = msg.get("code", "")

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        result_value = None

        try:
            with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                # Try exec first; if it's a single expression, eval it for its value
                try:
                    compiled = compile(code, "<data_agent>", "eval")
                    result_value = eval(compiled, _ns)
                except SyntaxError:
                    exec(compile(code, "<data_agent>", "exec"), _ns)

            figures = _capture_figures()

            # Auto-display DataFrame results
            display_text = None
            if result_value is not None:
                try:
                    if hasattr(result_value, "to_string"):
                        display_text = result_value.to_string(max_rows=50, max_cols=20)
                    else:
                        display_text = repr(result_value)
                except Exception:
                    display_text = str(result_value)

            response = {
                "ok": True,
                "stdout": stdout_capture.getvalue()[:64000],
                "stderr": stderr_capture.getvalue()[:8000],
                "display": display_text[:64000] if display_text else None,
                "figures": figures,
            }
        except Exception:
            tb = traceback.format_exc()
            figures = _capture_figures()
            response = {
                "ok": False,
                "stdout": stdout_capture.getvalue()[:64000],
                "stderr": tb[:16000],
                "display": None,
                "figures": figures,
            }

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

    except Exception as e:
        err = {"ok": False, "stdout": "", "stderr": str(e), "display": None, "figures": []}
        sys.stdout.write(json.dumps(err) + "\n")
        sys.stdout.flush()
'''


@dataclass
class ExecutionResult:
    """Result of executing Python code in the kernel."""

    success: bool
    stdout: str = ""
    stderr: str = ""
    display: str | None = None
    figures: list[dict[str, Any]] = field(default_factory=list)
    execution_time_ms: int = 0


class PythonKernel:
    """A stateful Python subprocess kernel tied to a session."""

    def __init__(self, session_id: str, dataset_dir: str | None = None):
        self.session_id = session_id
        self.kernel_id = str(uuid.uuid4())
        self._process: asyncio.subprocess.Process | None = None
        self._fig_dir = Path(tempfile.mkdtemp(prefix=f"dataagent_figs_{session_id[:8]}_"))
        self._dataset_dir = dataset_dir
        self._started = False

    async def start(self) -> None:
        """Start the kernel subprocess."""
        if self._started:
            return

        env = self._build_env()

        self._process = await asyncio.create_subprocess_exec(
            "python3", "-u", "-c", KERNEL_SCRIPT,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._started = True
        logger.info("Kernel %s started for session %s (pid=%s)", self.kernel_id, self.session_id, self._process.pid)

    async def execute(self, code: str, timeout: int = KERNEL_TIMEOUT) -> ExecutionResult:
        """Execute Python code in the kernel and return the result."""
        if not self._started or self._process is None:
            await self.start()

        assert self._process is not None
        assert self._process.stdin is not None
        assert self._process.stdout is not None

        import time
        t0 = time.perf_counter()

        msg = json.dumps({"code": code}) + "\n"
        self._process.stdin.write(msg.encode("utf-8"))
        await self._process.stdin.drain()

        try:
            raw = await asyncio.wait_for(self._process.stdout.readline(), timeout=timeout)
        except asyncio.TimeoutError:
            await self.restart()
            return ExecutionResult(
                success=False,
                stderr=f"Execution timed out after {timeout}s",
                execution_time_ms=int((time.perf_counter() - t0) * 1000),
            )

        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        if not raw:
            await self.restart()
            return ExecutionResult(
                success=False,
                stderr="Kernel process terminated unexpectedly",
                execution_time_ms=elapsed_ms,
            )

        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return ExecutionResult(
                success=False,
                stderr=f"Invalid kernel response: {raw.decode('utf-8', errors='replace')[:500]}",
                execution_time_ms=elapsed_ms,
            )

        return ExecutionResult(
            success=data.get("ok", False),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            display=data.get("display"),
            figures=data.get("figures", []),
            execution_time_ms=elapsed_ms,
        )

    async def restart(self) -> None:
        """Kill and restart the kernel."""
        await self.shutdown()
        await self.start()

    async def shutdown(self) -> None:
        """Terminate the kernel subprocess."""
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    self._process.kill()
                except ProcessLookupError:
                    pass
        self._process = None
        self._started = False
        logger.info("Kernel %s shut down for session %s", self.kernel_id, self.session_id)

    def _build_env(self) -> dict[str, str]:
        """Build a safe environment for the kernel subprocess."""
        safe_keys = {"PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM", "VIRTUAL_ENV", "PYTHONPATH"}
        env = {k: v for k, v in os.environ.items() if k in safe_keys}
        env["KERNEL_FIG_DIR"] = str(self._fig_dir)
        if self._dataset_dir:
            env["DATASET_DIR"] = self._dataset_dir
        return env


class KernelManager:
    """Manages multiple kernel instances, one per session."""

    def __init__(self):
        self._kernels: dict[str, PythonKernel] = {}
        self._figures_root = Path(settings.sandbox_workspace_root) / "figures"
        self._figures_root.mkdir(parents=True, exist_ok=True)

    async def get_or_create(self, session_id: str, dataset_dir: str | None = None) -> PythonKernel:
        """Get an existing kernel for the session, or create a new one."""
        if session_id not in self._kernels:
            kernel = PythonKernel(session_id, dataset_dir=dataset_dir)
            await kernel.start()
            self._kernels[session_id] = kernel
        return self._kernels[session_id]

    async def execute(self, session_id: str, code: str, dataset_dir: str | None = None) -> ExecutionResult:
        """Execute code in the session's kernel."""
        kernel = await self.get_or_create(session_id, dataset_dir=dataset_dir)
        result = await kernel.execute(code)
        # Convert inline base64 figures to disk-backed URLs
        if result.figures:
            result.figures = self._save_figures(session_id, result.figures)
        return result

    def _save_figures(self, session_id: str, figures: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Save base64-encoded figures to disk and replace with URL references."""
        session_dir = self._figures_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        converted = []
        for fig in figures:
            b64 = fig.get("data_base64")
            if not b64:
                converted.append(fig)
                continue
            try:
                png_bytes = base64.b64decode(b64)
                filename = f"{uuid.uuid4().hex}.png"
                filepath = session_dir / filename
                filepath.write_bytes(png_bytes)
                converted.append({
                    "url": f"/api/v1/data/figures/{session_id}/{filename}",
                    "format": fig.get("format", "png"),
                })
            except Exception:
                logger.warning("Failed to save figure to disk, keeping base64")
                converted.append(fig)
        return converted

    async def shutdown_session(self, session_id: str) -> None:
        """Shut down the kernel for a specific session."""
        if session_id in self._kernels:
            await self._kernels[session_id].shutdown()
            del self._kernels[session_id]

    async def shutdown_all(self) -> None:
        """Shut down all kernels."""
        for kernel in self._kernels.values():
            await kernel.shutdown()
        self._kernels.clear()


# Global kernel manager singleton
kernel_manager = KernelManager()
