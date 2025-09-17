import json
import os
import time
import uuid
from typing import Any, Dict, Optional


class Tracer:
    """
    Minimal JSONL tracer for Agent observability.

    Writes structured events to a JSONL file and keeps lightweight counters
    for API calls and token usage. Designed to be non-intrusive and resilient.
    """

    def __init__(self, jsonl_path: str = "./data/output/trace.jsonl") -> None:
        self.jsonl_path = jsonl_path
        os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
        self.session_id = str(uuid.uuid4())
        self.step = 0
        self._t0 = None
        self.counters = {
            "api_calls": 0,
            "token_in": 0,
            "token_out": 0,
        }

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def _write(self, obj: Dict[str, Any]) -> None:
        try:
            with open(self.jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        except Exception:
            # Tracing must never break the agent
            pass

    def log(self, etype: str, payload: Dict[str, Any]) -> None:
        event = {
            "session_id": self.session_id,
            "step": self.step,
            "type": etype,
            "ts": self._now_ms(),
            **payload,
        }
        self._write(event)

    def start_step(self, phase: str, meta: Optional[Dict[str, Any]] = None) -> None:
        self.step += 1
        self._t0 = time.perf_counter()
        self.log(phase, {"phase": phase, "status": "start", "meta": meta or {}})

    def end_step(self, phase: str, extra: Optional[Dict[str, Any]] = None) -> None:
        duration_ms = None
        if self._t0 is not None:
            duration_ms = int((time.perf_counter() - self._t0) * 1000)
        self.log(phase, {"phase": phase, "status": "end", "duration_ms": duration_ms, **(extra or {})})

    def incr_api(self, token_in: int = 0, token_out: int = 0) -> None:
        self.counters["api_calls"] += 1
        self.counters["token_in"] += max(int(token_in or 0), 0)
        self.counters["token_out"] += max(int(token_out or 0), 0)

    def finalize(self, result: str) -> None:
        self.log("final", {
            "status": "ok",
            "api_calls": self.counters["api_calls"],
            "token_in": self.counters["token_in"],
            "token_out": self.counters["token_out"],
            "result_preview": (result or "")[:300],
        })


