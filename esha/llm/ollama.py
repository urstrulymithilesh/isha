"""OllamaLLM — the real reasoning drop-in for Phase 1. Satisfies the LLM contract.

Talks to the local Ollama server over HTTP (stdlib only). Streams reply tokens so
TTS can start before the full reply is generated. keep_alive is sent as an INT
(-1 = keep resident); the string "-1" is rejected by Ollama with a 400 (learned
the hard way in the Phase 0 spike).
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Iterator, Sequence

from esha.config import CONFIG
from esha.core.interfaces import Message


class OllamaLLM:
    def __init__(self, *, host: str | None = None, model: str | None = None) -> None:
        cfg = CONFIG.reasoning
        self._host = host or cfg.ollama_host
        self._model = model or cfg.model
        self._keep_alive = cfg.keep_alive  # int -1
        self._num_ctx = cfg.num_ctx

    @property
    def supports_tools(self) -> bool:
        return True

    def chat(self, messages: Sequence[Message], *, stream: bool = True) -> Iterator[str]:
        body = json.dumps({
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
            "keep_alive": self._keep_alive,
            "options": {"num_ctx": self._num_ctx},
        }).encode()
        req = urllib.request.Request(
            f"{self._host}/api/chat", data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            if not stream:
                data = json.load(resp)
                yield data["message"]["content"]
                return
            for line in resp:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("done"):
                    break
                yield obj.get("message", {}).get("content", "")
