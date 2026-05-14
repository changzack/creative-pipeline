"""
Langfuse observability layer for Creative Pipeline V3.

Provides trace/span/generation tracking + prompt management with local-file
fallback. Uses the Langfuse v3 low-level API (no decorators needed for Python
3.9 compat).

Phase 1 additions (2026-05-12):
- Prompts manager: Langfuse-as-truth with local file fallback in pipeline/prompts/
- generation() context manager: tracks LLM calls with prompt_size metadata
- estimate_tokens(): char-based token estimate for non-API generators (Hermes)

Usage in pipeline.py:
    from langfuse_tracing import tracer, prompts

    # At run start:
    tracer.init()
    tracer.start_run("sharecard-v3", brief_text)

    # In each node:
    span = tracer.start_span("research", input={"brief": brief})
    # ... do work ...
    tracer.end_span(span, output={"result": "..."})

    # For LLM calls (preferred — context manager):
    with tracer.generation(
        name="approach-gate",
        model="claude-opus-4-7",
        input=prompt_text,
        prompt_obj=prompts.get("approach_gate"),
        metadata={"phase": "approach_gate"},
    ) as gen:
        response = client.messages.create(...)
        gen.set_output(response.content[0].text)
        gen.set_usage(input_tokens=..., output_tokens=...)

    # Prompts (Langfuse-as-truth):
    template = prompts.get("approach_gate").compile(approaches_text=text)

    # At run end:
    tracer.end_run(status="completed")
"""

import os
import time
import json
import contextlib
from pathlib import Path
from typing import Optional, Dict, Any, List, Iterator

# Langfuse SDK
try:
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False


# ── Token estimation ────────────────────────────────────────────
def estimate_tokens(text: str) -> int:
    """Rough char-based token estimate. Used when API doesn't report usage
    (e.g., Hermes subprocess calls). Conservative: ~3.5 chars/token."""
    if not text:
        return 0
    return max(1, len(text) // 4)


# ── Prompt management ──────────────────────────────────────────

PROMPTS_DIR = Path(__file__).parent / "prompts"


class _LocalPrompt:
    """Local-file prompt with the same compile() surface as a Langfuse prompt."""

    def __init__(self, name: str, template: str, source: str = "file"):
        self.name = name
        self.prompt = template
        self.version = None  # No version for local fallback
        self.source = source  # "file" or "langfuse"
        self.label = "local-fallback"

    def compile(self, **kwargs) -> str:
        """Substitute {{var}} placeholders with values."""
        out = self.prompt
        for key, value in kwargs.items():
            out = out.replace("{{" + key + "}}", str(value))
        return out


class Prompts:
    """Prompt manager. Langfuse-as-truth with local file fallback."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._client = None
        self._enabled = False
        self._label = "production"

    def attach_client(self, client, label: str = "production"):
        self._client = client
        self._enabled = client is not None
        self._label = label

    def _load_local(self, name: str) -> _LocalPrompt:
        path = PROMPTS_DIR / f"{name}.txt"
        if not path.exists():
            raise FileNotFoundError(f"Local prompt not found: {path}")
        return _LocalPrompt(name, path.read_text(), source="file")

    def get(self, name: str):
        """Fetch a prompt by name. Tries Langfuse first, falls back to local file.
        Cached per process — call invalidate() to force refresh."""
        if name in self._cache:
            return self._cache[name]

        prompt = None
        # Try Langfuse first
        if self._enabled and self._client:
            try:
                p = self._client.get_prompt(name, label=self._label)
                # Wrap so .source is set consistently
                p.source = "langfuse"
                prompt = p
                print(f"  📜 prompt '{name}' loaded from Langfuse (v{getattr(p, 'version', '?')})")
            except Exception as e:
                print(f"  ⚠️  Langfuse prompt fetch failed for '{name}' — falling back to file ({e})")

        # Fallback to local file
        if prompt is None:
            prompt = self._load_local(name)
            print(f"  📜 prompt '{name}' loaded from local file")

        self._cache[name] = prompt
        return prompt

    def invalidate(self, name: str = None):
        if name:
            self._cache.pop(name, None)
        else:
            self._cache.clear()


# ── Generation context manager ─────────────────────────────────

class _GenerationCtx:
    """Wraps a Langfuse generation with set_output/set_usage helpers."""

    def __init__(self, gen, input_text: str, prompt_obj: Any = None,
                 metadata: Dict = None):
        self._gen = gen
        self._input_text = input_text
        self._prompt_obj = prompt_obj
        self._metadata = dict(metadata or {})
        self._output: Optional[str] = None
        self._usage: Optional[Dict[str, int]] = None
        self._level: Optional[str] = None
        self._status_message: Optional[str] = None
        self._start_time = time.time()

    def set_output(self, text: Any):
        self._output = text

    def set_usage(self, input_tokens: int = None, output_tokens: int = None,
                  total_tokens: int = None, estimated: bool = False):
        usage = {}
        if input_tokens is not None:
            usage["input"] = int(input_tokens)
        if output_tokens is not None:
            usage["output"] = int(output_tokens)
        if total_tokens is not None:
            usage["total"] = int(total_tokens)
        if estimated:
            self._metadata["token_usage_estimated"] = True
        self._usage = usage

    def set_error(self, message: str):
        self._level = "ERROR"
        self._status_message = message

    def add_metadata(self, **kwargs):
        self._metadata.update(kwargs)

    def finalize(self):
        if self._gen is None:
            return
        try:
            update_kwargs: Dict[str, Any] = {}
            if self._output is not None:
                update_kwargs["output"] = _safe_serialize(self._output)
            if self._usage:
                update_kwargs["usage_details"] = self._usage

            # Bake in prompt-size metadata + duration
            meta = dict(self._metadata)
            meta["prompt_chars"] = len(self._input_text) if self._input_text else 0
            meta["prompt_chars_estimated_tokens"] = estimate_tokens(self._input_text) if self._input_text else 0
            meta["duration_seconds"] = round(time.time() - self._start_time, 2)
            if self._prompt_obj is not None:
                meta["prompt_source"] = getattr(self._prompt_obj, "source", "unknown")
                meta["prompt_name"] = getattr(self._prompt_obj, "name", "unknown")
                meta["prompt_version"] = getattr(self._prompt_obj, "version", None)
                meta["prompt_label"] = getattr(self._prompt_obj, "label", None)
            update_kwargs["metadata"] = meta

            if self._level:
                update_kwargs["level"] = self._level
            if self._status_message:
                update_kwargs["status_message"] = self._status_message

            self._gen.update(**update_kwargs)
            self._gen.end()
        except Exception as e:
            print(f"  ⚠️  Langfuse generation finalize failed: {e}")


class PipelineTracer:
    """Wraps Langfuse client for pipeline observability."""

    def __init__(self):
        self._client = None  # type: Optional[Langfuse]
        self._trace_id = None  # str trace ID
        self._root_span = None  # root span for the run
        self._spans = {}  # span_name -> span object
        self._run_name = None
        self._session_id = None  # groups all traces from the same pipeline run
        self._enabled = False
        self._trace_context = None

    def init(self,
             public_key: str = None,
             secret_key: str = None,
             host: str = None,
             prompt_label: str = "production"):
        """Initialize Langfuse client. Call once at startup."""
        if not LANGFUSE_AVAILABLE:
            print("  ⚠️  langfuse not installed, tracing disabled")
            prompts.attach_client(None)
            return

        try:
            self._client = Langfuse(
                public_key=public_key or os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-lf-pipeline-v3"),
                secret_key=secret_key or os.environ.get("LANGFUSE_SECRET_KEY", "sk-lf-pipeline-v3-secret2026"),
                host=host or os.environ.get("LANGFUSE_HOST", "http://localhost:3000"),
            )
            self._enabled = True
            prompts.attach_client(self._client, label=prompt_label)
            print("  ✅ Langfuse tracing initialized")
        except Exception as e:
            print(f"  ⚠️  Langfuse init failed: {e}")
            self._enabled = False
            prompts.attach_client(None)

    def start_run(self, run_name: str, brief: str = "", metadata: Dict = None,
                  session_id: str = None):
        """Create a top-level trace for a pipeline run using v3 context API.

        session_id groups multiple traces (initial run, resumes, crash recoveries)
        under one Langfuse Session for end-to-end viewing. Defaults to the base
        run name (stripped of -resume / -crash-recover suffixes) so every trace
        for the same logical pipeline run lands in the same session.
        """
        if not self._enabled:
            return None
        self._run_name = run_name
        # Derive a stable session_id by stripping known per-trace suffixes
        if session_id is None:
            base = run_name
            for suffix in ("-crash-recover", "-resume"):
                if base.endswith(suffix):
                    base = base[: -len(suffix)]
                    break
            session_id = base
        self._session_id = session_id
        self._trace_id = self._client.create_trace_id()
        self._trace_context = {"trace_id": self._trace_id}
        try:
            self._root_span = self._client.start_span(
                name=f"pipeline-{run_name}",
                trace_context=self._trace_context,
                input=_safe_serialize({"brief": brief[:2000]}),
                metadata={
                    "run_name": run_name,
                    "session_id": session_id,
                    "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    **(metadata or {}),
                },
            )
            # Attach trace-level session_id so Langfuse groups this trace under
            # the run's session. Must be called inside the root-span context.
            try:
                with self._root_span.start_as_current_span(name="_trace_init") as _init:
                    self._client.update_current_trace(
                        session_id=session_id,
                        name=f"pipeline-{run_name}",
                    )
            except Exception as e:
                print(f"  ⚠️  Could not attach session_id at trace start ({e}) — will retry at end_run")
            print(f"  📊 Langfuse trace started: {self._trace_id} (session={session_id})")
            return self._trace_id
        except Exception as e:
            print(f"  ⚠️  Langfuse trace creation failed: {e}")
            return None

    @property
    def session_id(self):
        return self._session_id

    @property
    def trace_id(self):
        return self._trace_id

    def start_span(self, name: str, input: Any = None, metadata: Dict = None) -> Optional[Any]:
        """Start a span (pipeline node / phase)."""
        if not self._enabled or not self._trace_id:
            return None
        try:
            span = self._client.start_span(
                name=name,
                trace_context=self._trace_context,
                input=_safe_serialize(input),
                metadata=metadata,
            )
            self._spans[name] = span
            return span
        except Exception as e:
            print(f"  ⚠️  Langfuse span start failed ({name}): {e}")
            return None

    def end_span(self, span_or_name, output: Any = None,
                 metadata: Dict = None, level: str = None):
        """End a span with output."""
        if not self._enabled:
            return
        try:
            span = span_or_name if not isinstance(span_or_name, str) else self._spans.get(span_or_name)
            if span:
                update_kwargs = {}
                if output is not None:
                    update_kwargs["output"] = _safe_serialize(output)
                if metadata:
                    update_kwargs["metadata"] = metadata
                if level:
                    update_kwargs["level"] = level
                if update_kwargs:
                    span.update(**update_kwargs)
                span.end()
        except Exception as e:
            print(f"  ⚠️  Langfuse span end failed: {e}")

    @contextlib.contextmanager
    def generation(self,
                   name: str,
                   model: str,
                   input: Any = None,
                   prompt_obj: Any = None,
                   model_parameters: Dict = None,
                   metadata: Dict = None) -> Iterator[_GenerationCtx]:
        """Context manager for LLM generations. Auto-finalizes on exit.

        Usage:
            with tracer.generation(name="judge", model="gpt-4o", input=prompt) as gen:
                resp = client.chat.completions.create(...)
                gen.set_output(resp.choices[0].message.content)
                gen.set_usage(input_tokens=resp.usage.prompt_tokens,
                              output_tokens=resp.usage.completion_tokens)
        """
        gen = None
        if self._enabled and self._trace_id:
            try:
                gen_kwargs = {
                    "name": name,
                    "trace_context": self._trace_context,
                    "model": model,
                    "input": _safe_serialize(input),
                }
                if model_parameters:
                    gen_kwargs["model_parameters"] = model_parameters
                if metadata:
                    gen_kwargs["metadata"] = metadata
                if prompt_obj is not None:
                    # Only pass to Langfuse if it's an actual Langfuse prompt object
                    # (local fallbacks don't have a server-side version to link)
                    if getattr(prompt_obj, "source", None) == "langfuse":
                        gen_kwargs["prompt"] = prompt_obj
                gen = self._client.start_generation(**gen_kwargs)
            except Exception as e:
                print(f"  ⚠️  Langfuse generation start failed ({name}): {e}")
                gen = None

        ctx = _GenerationCtx(gen, input_text=input if isinstance(input, str) else "",
                             prompt_obj=prompt_obj, metadata=metadata or {})
        try:
            yield ctx
        except Exception as e:
            ctx.set_error(str(e)[:500])
            raise
        finally:
            ctx.finalize()

    def start_generation(self, name: str, model: str,
                         input: Any = None,
                         model_parameters: Dict = None,
                         metadata: Dict = None,
                         parent_span: Any = None) -> Optional[Any]:
        """Track an LLM generation (legacy non-context-manager API)."""
        if not self._enabled or not self._trace_id:
            return None
        try:
            gen = self._client.start_generation(
                name=name,
                trace_context=self._trace_context,
                model=model,
                input=_safe_serialize(input),
                model_parameters=model_parameters,
                metadata=metadata,
            )
            return gen
        except Exception as e:
            print(f"  ⚠️  Langfuse generation start failed ({name}): {e}")
            return None

    def end_generation(self, gen, output: Any = None,
                       usage: Dict = None, metadata: Dict = None,
                       level: str = None):
        """End an LLM generation (legacy API)."""
        if not self._enabled or not gen:
            return
        try:
            update_kwargs = {}
            if output is not None:
                update_kwargs["output"] = _safe_serialize(output)
            if usage:
                update_kwargs["usage_details"] = usage
            if metadata:
                update_kwargs["metadata"] = metadata
            if level:
                update_kwargs["level"] = level
            if update_kwargs:
                gen.update(**update_kwargs)
            gen.end()
        except Exception as e:
            print(f"  ⚠️  Langfuse generation end failed: {e}")

    def score(self, name: str, value: float, comment: str = None,
              observation_id: str = None):
        """Add a score to the current trace (e.g., human rating, judge score)."""
        if not self._enabled or not self._trace_id:
            return
        try:
            self._client.create_score(
                name=name,
                value=value,
                trace_id=self._trace_id,
                comment=comment,
                observation_id=observation_id,
            )
        except Exception as e:
            print(f"  ⚠️  Langfuse score failed ({name}): {e}")

    def end_run(self, status: str = "completed", output: Any = None,
                metadata: Dict = None, tags: Optional[list] = None):
        """Finalize the root span and flush. Optionally attach trace-level tags."""
        if not self._enabled:
            return
        try:
            # Allow tags to be passed inside metadata for convenience
            meta = dict(metadata or {})
            extracted_tags = meta.pop("tags", None)
            final_tags = tags if tags is not None else extracted_tags

            if self._root_span:
                # Trace-level fields (tags, name, output) via update_current_trace,
                # which needs to run inside the span's active context. Fall back
                # to span.update() for metadata that doesn't have a trace-level home.
                try:
                    # update_current_trace uses the implicit OTEL context. The root span
                    # is the active span at this point because we never called .end() yet.
                    with self._root_span.start_as_current_span(name="_trace_finalize") as _fin:
                        update_kwargs = {
                            "name": f"pipeline-{self._run_name}" if self._run_name else None,
                            "session_id": self._session_id,
                            "output": _safe_serialize(output) if output is not None else None,
                            "metadata": {
                                "status": status,
                                "session_id": self._session_id,
                                "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                **meta,
                            },
                        }
                        if final_tags:
                            update_kwargs["tags"] = list(final_tags)
                        # Drop None values
                        update_kwargs = {k: v for k, v in update_kwargs.items() if v is not None}
                        self._client.update_current_trace(**update_kwargs)
                except Exception as e:
                    print(f"  ⚠️  update_current_trace failed (continuing): {e}")

                # Mirror status + metadata on the root span itself for observation-level views
                self._root_span.update(
                    output=_safe_serialize(output),
                    metadata={
                        "status": status,
                        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        **meta,
                        **({"tags": list(final_tags)} if final_tags else {}),
                    },
                )
                self._root_span.end()
            self._client.flush()
            print(f"  📊 Langfuse trace: http://localhost:3000/trace/{self._trace_id}")
        except Exception as e:
            print(f"  ⚠️  Langfuse end_run failed: {e}")

    def flush(self):
        """Flush pending events."""
        if self._enabled and self._client:
            try:
                self._client.flush()
            except Exception:
                pass


def _safe_serialize(obj: Any, max_len: int = 10000) -> Any:
    """Safely serialize objects for Langfuse, truncating large values."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        if isinstance(obj, str) and len(obj) > max_len:
            return obj[:max_len] + f"... [truncated, {len(obj)} chars total]"
        return obj
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(item, max_len) for item in obj[:50]]
    if isinstance(obj, dict):
        return {k: _safe_serialize(v, max_len) for k, v in list(obj.items())[:50]}
    if isinstance(obj, Path):
        return str(obj)
    try:
        s = json.dumps(obj, default=str)
        if len(s) > max_len:
            return s[:max_len] + "..."
        return json.loads(s)
    except Exception:
        return str(obj)[:max_len]


# Singleton instances
tracer = PipelineTracer()
prompts = Prompts()
