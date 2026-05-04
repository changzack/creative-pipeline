"""
Langfuse observability layer for Creative Pipeline V3.

Provides trace/span/generation tracking without invasive changes to pipeline.py.
Uses the Langfuse v3 low-level API (no decorators needed for Python 3.9 compat).

Usage in pipeline.py:
    from langfuse_tracing import tracer
    
    # At run start:
    tracer.start_run("my-run", brief_text)
    
    # In each node:
    span = tracer.start_span("research", input={"brief": brief})
    # ... do work ...
    tracer.end_span(span, output={"result": "..."}, cost=0.05)
    
    # For LLM calls:
    gen = tracer.start_generation("research-llm", model="claude-opus-4-6", input=[...])
    # ... call LLM ...
    tracer.end_generation(gen, output="...", usage={"input": 1000, "output": 500})
    
    # At run end:
    tracer.end_run(status="completed", metadata={...})
"""

import os
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

# Langfuse SDK
try:
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False


class PipelineTracer:
    """Wraps Langfuse client for pipeline observability."""
    
    def __init__(self):
        self._client = None  # type: Optional[Langfuse]
        self._trace_id = None  # str trace ID
        self._root_span = None  # root span for the run
        self._spans = {}  # span_name -> span object
        self._run_name = None
        self._enabled = False
    
    def init(self, 
             public_key: str = None,
             secret_key: str = None,
             host: str = None):
        """Initialize Langfuse client. Call once at startup."""
        if not LANGFUSE_AVAILABLE:
            print("  ⚠️  langfuse not installed, tracing disabled")
            return
        
        try:
            self._client = Langfuse(
                public_key=public_key or os.environ.get("LANGFUSE_PUBLIC_KEY", "your-public-key"),
                secret_key=secret_key or os.environ.get("LANGFUSE_SECRET_KEY", "your-secret-key"),
                host=host or os.environ.get("LANGFUSE_HOST", "http://localhost:3000"),
            )
            self._enabled = True
            print("  ✅ Langfuse tracing initialized")
        except Exception as e:
            print(f"  ⚠️  Langfuse init failed: {e}")
            self._enabled = False
    
    def start_run(self, run_name: str, brief: str = "", metadata: Dict = None):
        """Create a top-level trace for a pipeline run using v3 context API."""
        if not self._enabled:
            return None
        self._run_name = run_name
        self._trace_id = self._client.create_trace_id()
        self._trace_context = {"trace_id": self._trace_id}
        try:
            self._root_span = self._client.start_span(
                name=f"pipeline-{run_name}",
                trace_context=self._trace_context,
                input=_safe_serialize({"brief": brief[:2000]}),
                metadata={
                    "run_name": run_name,
                    "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    **(metadata or {}),
                },
            )
            print(f"  📊 Langfuse trace started: {self._trace_id}")
            return self._trace_id
        except Exception as e:
            print(f"  ⚠️  Langfuse trace creation failed: {e}")
            return None
    
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
    
    def start_generation(self, name: str, model: str, 
                         input: Any = None, 
                         model_parameters: Dict = None,
                         metadata: Dict = None,
                         parent_span: Any = None) -> Optional[Any]:
        """Track an LLM generation (prompt → completion)."""
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
        """End an LLM generation with output and token usage."""
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
                metadata: Dict = None):
        """Finalize the root span and flush."""
        if not self._enabled:
            return
        try:
            if self._root_span:
                self._root_span.update(
                    output=_safe_serialize(output),
                    metadata={
                        "status": status,
                        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        **(metadata or {}),
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


# Singleton tracer instance
tracer = PipelineTracer()
