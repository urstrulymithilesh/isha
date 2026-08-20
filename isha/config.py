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
    # qwen2.5:3b is the design doc's PRIMARY pick (stronger instruction-following +
    # tool-calling) and ~1.9GB Q4 fits the 4GB GPU by size. NOTE: as of this machine's
    # Ollama build it still runs ~12 tok/s on CPU (both qwen2.5:3b and llama3.2) because
    # Ollama's Vulkan GPU discovery watchdog times out ("context deadline exceeded") and
    # falls back to CPU — see server.log. GPU enablement is a separate task; ~12 tok/s
    # CPU is usable for turn-based voice. llama3.2 stays the A/B baseline (persona eval T6).
    # Default is qwen2.5:7b: it grounds on injected memory RELIABLY where 3b confabulated
    # (invented facts, hallucinated details) — a companion inventing facts about you is a
    # worse failure than a slower one. Cost: ~14-17s/reply on CPU (3b was ~3-5s); streaming
    # TTS softens that wait. Switch to "qwen2.5:3b" for speed if you accept flaky memory.
    model: str = "qwen2.5:7b"
    keep_alive: int = -1                # keep the model resident in VRAM (Ollama: int -1 = forever; "-1" string is rejected)
    num_ctx: int = 4096                 # cap KV/context so Windows-reserved VRAM doesn't OOM the 4GB
    temperature: float = 0.6            # 0.8 made her over-improvise (question every turn);
                                        # 0.6 follows the persona's "don't always ask" rule better
    # Fraction of the time a reflexive trailing question is KEPT (rest are trimmed by
    # reply_style). 0 = always trim, 1 = never trim. The 3B asks too much on its own.
    question_keep_rate: float = 0.4
    request_timeout: int = 90           # seconds; CPU generation is slow, but this bounds a hang


@dataclass(frozen=True)
class SpeechConfig:
    # CPU = hear + speak.
    whisper_model: str = "base.en"      # faster-whisper, int8, on CPU
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    sample_rate: int = 16_000           # pipeline INPUT convention: 16 kHz mono
    # Piper via the piper-tts Python API (no PATH binary). The voice .onnx (+ .json)
    # lives in models/; download with `python -m piper.download_voices <voice> --download-dir models`.
    # 22050 Hz — playback uses the voice's own rate, input stays 16k. amy-medium (warmer).
    piper_voice: str = "en_US-amy-medium"


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
    vad_silence_ms: int = 950           # trailing silence that ends a turn. Single-number
                                        # trade-off: 700 cut people off mid-sentence, 1100 felt
                                        # laggy after finishing; ~950 is the middle. Tune by feel.
    vad_min_speech_ms: int = 300        # need this much speech before a silence can end a turn
    preroll_ms: int = 500               # audio kept BEFORE the wake fires, prepended to the
                                        # turn so the start of your sentence isn't lost
    # Measure room + a test phrase on `isha run` startup and set gain + threshold.
    auto_calibrate: bool = True


@dataclass(frozen=True)
class WakeConfig:
    # Stock openWakeWord model until the custom "Isha" word is trained in Phase 4.
    model: str = "hey_jarvis"           # placeholder stock word; retrain to "Isha" later
    stop_word: str = "hey_jarvis"       # kept live during SPEAKING to allow barge-in


@dataclass(frozen=True)
class MemoryConfig:
    db_path: Path = DATA_DIR / "isha.db"
    embedder_model: str = "BAAI/bge-small-en-v1.5"  # CPU (fastembed) — must NOT be a GPU model
    recall_k: int = 3                   # strict read budget: top-3 facts per turn
    recent_turns: int = 12              # rolling history kept in context
    context_char_budget: int = 2400     # cap on the recent-turns tail (~600 tokens); keeps
                                        # persona + facts + history well under num_ctx (4096)
    min_fact_confidence: float = 0.6    # gate out low-confidence extracted facts


@dataclass(frozen=True)
class Config:
    reasoning: ReasoningConfig = field(default_factory=ReasoningConfig)
    speech: SpeechConfig = field(default_factory=SpeechConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    wake: WakeConfig = field(default_factory=WakeConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)


CONFIG = Config()
