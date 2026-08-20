"""PiperSynthesizer — the real v1 TTS, a clean drop-in for StubSynthesizer.

Shells out to the Piper BINARY (the pip package is flaky on Windows). Piper writes
raw 16-bit PCM to stdout, which we chunk into the pipeline's frame size and stream
so playback can start immediately and be interrupted by a stop-word.

Not wired in until you install the binary — the factory picks StubSynthesizer when
`piper` is not on PATH, and this class the moment it is. Setup:
  1. Download the Windows release from github.com/rhasspy/piper/releases
  2. Download a voice (.onnx + .onnx.json), e.g. en_US-amy-medium
  3. Put `piper` on PATH (or set an absolute path in config), then just re-run.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator

from esha.audio.frames import CHUNK_BYTES, SAMPLE_RATE
from esha.config import CONFIG


class PiperSynthesizer:
    def __init__(self, *, binary: str | None = None, voice: str | None = None) -> None:
        self._binary = binary or CONFIG.speech.piper_binary
        self._voice = voice or CONFIG.speech.piper_voice

    @staticmethod
    def is_available(binary: str | None = None) -> bool:
        return shutil.which(binary or CONFIG.speech.piper_binary) is not None

    def synthesize(self, text: str) -> Iterator[bytes]:
        proc = subprocess.Popen(
            [self._binary, "--model", self._voice, "--output_raw",
             "--sample_rate", str(SAMPLE_RATE)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(text.encode("utf-8"))
        proc.stdin.close()
        try:
            while True:
                chunk = proc.stdout.read(CHUNK_BYTES)
                if not chunk:
                    break
                yield chunk
        finally:
            proc.wait()
