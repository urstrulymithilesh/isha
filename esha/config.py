"""Central config. Swapping a model or engine later is a change HERE, not in code.

Every value is chosen to honor the fully-local, offline, CPU/GPU-split design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# All runtime data stays local and private (gitignored).
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


@dataclass(frozen=True)
class ReasoningConfig:
    # GPU = reason. Qwen pinned resident so first-token latency stays low.
    ollama_host: str = "http://localhost:11434"
    # llama3.2 (3B) is already local and is the design's documented A/B baseline, so
    # v1 starts here for zero-download momentum. The doc's PRIMARY pick is qwen2.5:3b
    # (stronger tool-calling) — `ollama pull qwen2.5:3b`, then set model="qwen2.5:3b"
    # and A/B them with the persona eval (T6). Swap to 7B/14B after a GPU upgrade.
    model: str = "llama3.2"
    keep_alive: int = -1                # keep the model resident in VRAM (Ollama: int -1 = forever; "-1" string is rejected)
    num_ctx: int = 4096                 # cap KV/context so Windows-reserved VRAM doesn't OOM the 4GB


@dataclass(frozen=True)
class SpeechConfig:
    # CPU = hear + speak.
    whisper_model: str = "base.en"      # faster-whisper, int8, on CPU
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    sample_rate: int = 16_000           # pipeline INPUT convention: 16 kHz mono
    # Piper via the piper-tts Python API (no PATH binary). The voice .onnx (+ .json)
    # lives in models/; download with `python -m piper.download_voices <voice> --download-dir models`.
    # Lessac medium is 22050 Hz — playback uses the voice's own rate, input stays 16k.
    piper_voice: str = "en_US-lessac-medium"


@dataclass(frozen=True)
class AudioConfig:
    # Device INDICES from `python diagnose.py`. None = OS default (often the wrong
    # one — the built-in mic array, not your headset). Set input_device to your
    # headset mic's index once diagnose.py confirms the VU meter moves.
    input_device: int | None = None
    output_device: int | None = None
    # Software capture gain — boosts quiet laptop mics so speech is loud enough for
    # both VAD and STT, without touching Windows mic settings. 1.0 = off.
    # Auto-calibration overrides this at startup unless auto_calibrate is False.
    capture_gain: float = 1.0
    # RMS level (POST-gain) a frame must exceed to count as speech. 500 was too high
    # for laptop mics; auto-calibration sets a real value from your room + voice.
    vad_threshold: float = 150.0
    vad_silence_ms: int = 700           # trailing silence that ends a turn
    # Measure room + a test phrase on `esha run` startup and set gain + threshold.
    auto_calibrate: bool = True


@dataclass(frozen=True)
class WakeConfig:
    # Stock openWakeWord model until the custom "Esha" word is trained in Phase 4.
    model: str = "hey_jarvis"           # placeholder stock word; retrain to "Esha" later
    stop_word: str = "hey_jarvis"       # kept live during SPEAKING to allow barge-in


@dataclass(frozen=True)
class MemoryConfig:
    db_path: Path = DATA_DIR / "esha.db"
    embedder_model: str = "BAAI/bge-small-en-v1.5"  # CPU (fastembed) — must NOT be a GPU model
    recall_k: int = 3                   # strict read budget: top-3 facts per turn
    recent_turns: int = 12              # rolling history kept in context
    min_fact_confidence: float = 0.6    # gate out low-confidence extracted facts


@dataclass(frozen=True)
class Config:
    reasoning: ReasoningConfig = field(default_factory=ReasoningConfig)
    speech: SpeechConfig = field(default_factory=SpeechConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    wake: WakeConfig = field(default_factory=WakeConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)


CONFIG = Config()
