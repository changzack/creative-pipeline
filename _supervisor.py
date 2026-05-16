"""Supervisor event/heartbeat/cost emitters for pipeline.py.

Pass 1 of better-supervision. NEVER raises. NEVER blocks the pipeline.
Best-effort writes. On any I/O error: log to stderr, swallow, continue.

Streams:
  /tmp/pipeline-runs/{name}.events.jsonl    — structured event log
  /tmp/pipeline-runs/{name}.heartbeat        — last-known phase/cost (overwritten ~30s)
  /tmp/pipeline-runs/{name}.exit-code        — numeric only, written at shutdown()
  ~/.openclaw/workspace/overnight-runs/{name}/cost.jsonl  — append-per-cost-call

Public API:
  init(run_name, cost_getter=None) — call once at run start
  set_current_phase(phase)         — call at the start of each node
  emit_event(event, **kwargs)      — append one JSONL line
  emit_cost(model, in_tokens, out_tokens, delta_usd, total_usd, phase) — cost stream + event
  shutdown(verdict, exception=None, total_usd=0.0) — terminal event + stop heartbeat
  supervised(phase)                — decorator: wraps node fn with phase_enter/complete
"""
from __future__ import annotations

import json
import os
import sys
import time
import threading
import functools
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Callable, Optional

_EVENTS_DIR = Path("/tmp/pipeline-runs")
_RUN_DIR_BASE = Path.home() / ".openclaw" / "workspace" / "overnight-runs"

_state = {
    "run_name": None,
    "events_path": None,
    "cost_path": None,
    "heartbeat_path": None,
    "exit_code_path": None,
    "heartbeat_thread": None,
    "heartbeat_stop": None,
    "start_ts": None,
    "current_phase": "init",
    "cost_getter": None,  # callable() -> float
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _warn(msg: str) -> None:
    try:
        sys.stderr.write(f"[supervisor] {msg}\n")
    except Exception:
        pass


def _append_jsonl(path: Optional[Path], payload: dict) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, default=str)
        # Line-buffered open: each line flushes on newline.
        with path.open("a", buffering=1) as f:
            f.write(line + "\n")
    except Exception as e:
        _warn(f"jsonl write failed ({path}): {e}")


def init(run_name: str, cost_getter: Optional[Callable[[], float]] = None) -> None:
    """Call once at pipeline start (per process). Safe to call again with the
    same run_name; subsequent calls are silent no-ops. Different run_name
    replaces state — useful if a process serves multiple runs."""
    try:
        if _state["run_name"] == run_name:
            return
        _EVENTS_DIR.mkdir(parents=True, exist_ok=True)
        _state["run_name"] = run_name
        _state["events_path"] = _EVENTS_DIR / f"{run_name}.events.jsonl"
        _state["heartbeat_path"] = _EVENTS_DIR / f"{run_name}.heartbeat"
        _state["exit_code_path"] = _EVENTS_DIR / f"{run_name}.exit-code"
        _state["cost_path"] = _RUN_DIR_BASE / run_name / "cost.jsonl"
        _state["start_ts"] = time.time()
        _state["current_phase"] = "init"
        _state["cost_getter"] = cost_getter

        # Kick off heartbeat thread.
        stop = threading.Event()
        _state["heartbeat_stop"] = stop
        t = threading.Thread(target=_heartbeat_loop, args=(stop,), daemon=True, name="supervisor-hb")
        _state["heartbeat_thread"] = t
        t.start()

        emit_event("phase_enter", phase="init")
    except Exception as e:
        _warn(f"init failed: {e}")


def set_current_phase(phase: str) -> None:
    try:
        _state["current_phase"] = phase
    except Exception:
        pass


def emit_event(event: str, **kwargs: Any) -> None:
    """Append one JSONL line to events.jsonl. Best-effort."""
    try:
        payload = {"ts": _iso_now(), "event": event}
        payload.update(kwargs)
        _append_jsonl(_state["events_path"], payload)
    except Exception as e:
        _warn(f"emit_event failed: {e}")


def emit_cost(model: str, in_tokens: int, out_tokens: int,
              delta_usd: float, total_usd: float, phase: str) -> None:
    """Append to cost.jsonl AND emit a cost_update event. Both best-effort."""
    try:
        cost_payload = {
            "ts": _iso_now(),
            "phase": phase,
            "model": model,
            "in": int(in_tokens or 0),
            "out": int(out_tokens or 0),
            "delta_usd": round(float(delta_usd or 0.0), 6),
            "total_usd": round(float(total_usd or 0.0), 6),
        }
        _append_jsonl(_state["cost_path"], cost_payload)
    except Exception as e:
        _warn(f"emit_cost (cost.jsonl) failed: {e}")
    try:
        emit_event(
            "cost_update",
            total_usd=round(float(total_usd or 0.0), 6),
            phase=phase,
            model=model,
            delta_usd=round(float(delta_usd or 0.0), 6),
        )
    except Exception as e:
        _warn(f"emit_cost (event) failed: {e}")


def _current_cost() -> float:
    fn = _state.get("cost_getter")
    if fn is None:
        return 0.0
    try:
        return float(fn() or 0.0)
    except Exception:
        return 0.0


def _heartbeat_loop(stop: threading.Event) -> None:
    """Every 30s, atomically overwrite the heartbeat file. Checks stop every 1s."""
    path = _state.get("heartbeat_path")
    if path is None:
        return
    # Write one immediately so the file exists as soon as init() returns.
    _write_heartbeat()
    elapsed = 0
    while not stop.is_set():
        if stop.wait(1.0):
            break
        elapsed += 1
        if elapsed >= 30:
            elapsed = 0
            _write_heartbeat()


def _write_heartbeat() -> None:
    path = _state.get("heartbeat_path")
    if path is None:
        return
    try:
        start_ts = _state.get("start_ts") or time.time()
        payload = {
            "ts": _iso_now(),
            "phase": _state.get("current_phase") or "unknown",
            "cost_usd": round(_current_cost(), 6),
            "elapsed_s": int(time.time() - start_ts),
        }
        # Atomic-ish overwrite via tmp + rename.
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload))
        os.replace(tmp, path)
    except Exception as e:
        _warn(f"heartbeat write failed: {e}")


def shutdown(verdict: str, exception: Optional[str] = None,
             total_usd: float = 0.0) -> None:
    """Final terminal event + stop heartbeat thread + write exit-code file.

    verdict: 'completed' | 'failed' | 'killed' | 'degraded'
    exit_code mapping: completed=0, killed=143, failed/degraded=1
    """
    try:
        emit_event("terminal", verdict=verdict,
                   cost_usd=round(float(total_usd or 0.0), 6),
                   exception=exception)
    except Exception as e:
        _warn(f"shutdown emit_event failed: {e}")
    try:
        stop = _state.get("heartbeat_stop")
        if stop is not None:
            stop.set()
        t = _state.get("heartbeat_thread")
        if t is not None and t.is_alive():
            t.join(timeout=2.0)
    except Exception as e:
        _warn(f"shutdown heartbeat stop failed: {e}")
    try:
        code = {"completed": 0, "killed": 143}.get(verdict, 1)
        ep = _state.get("exit_code_path")
        if ep is not None:
            ep.parent.mkdir(parents=True, exist_ok=True)
            ep.write_text(str(code))
    except Exception as e:
        _warn(f"shutdown exit-code write failed: {e}")


def supervised(phase: str):
    """Decorator: emit phase_enter/phase_complete around a node function.

    Used for all node functions that have multiple returns or where inline
    hooks would clutter readability. For nodes with payload-bearing event
    enrichment (e.g. polish_loop_node with loop_type), wire hooks inline
    instead.
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                set_current_phase(phase)
                emit_event("phase_enter", phase=phase)
            except Exception:
                pass
            t0 = time.time()
            try:
                return fn(*args, **kwargs)
            finally:
                try:
                    emit_event(
                        "phase_complete",
                        phase=phase,
                        elapsed_s=int(time.time() - t0),
                        cost_usd=round(_current_cost(), 6),
                    )
                except Exception:
                    pass
        return wrapper
    return deco
