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
    # Back on qwen2.5:3b for fast day-to-day iteration (~3-5s replies, ~3-5s extraction).
    # STORAGE/extraction is reliable on 3b; RECALL grounding is occasionally flaky (3b can
    # confabulate around an injected fact). 7b grounds far better but ~15s/reply + ~15s
    # extraction is too much dead time to iterate through. Swap back to "qwen2.5:7b" (or a
    # better model / GPU) later — this is exactly the swap the LLM interface was built for.
    model: str = "llama3.2"
    keep_alive: int = -1                # keep the model resident in VRAM (Ollama: int -1 = forever; "-1" string is rejected)
    num_ctx: int = 4096                 # cap KV/context so Windows-reserved VRAM doesn't OOM the 4GB
    temperature: float = 0.6            # 0.8 made her over-improvise (question every turn);
                                        # 0.6 follows the persona's "don't always ask" rule better
    # Fraction of the time a reflexive trailing question is KEPT (rest are trimmed by
    # reply_style). 0 = always trim, 1 = never trim. The 3B asks too much on its own.
    question_keep_rate: float = 0.15
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
    # If a wake fires but no speech follows (a false trigger, or a barge-in where he
    # changed his mind), give up after this and go back to sleep instead of listening
    # forever — a silent LISTENING state looks exactly like a crash from outside.
    listen_timeout_ms: int = 8000
    # Once engaged, she keeps listening between turns with no wake word. The window is
    # much longer than the post-wake one (a pause mid-conversation is normal), but it is
    # NOT infinite on purpose: a false VAD trigger on room noise would otherwise start
    # junk turns forever, and a mic that never closes is a privacy regression.
    continuous_timeout_ms: int = 45000
    continuous_mode: bool = True
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
    catch_up_limit: int = 5             # max unfinished exchanges re-extracted at startup
    # Two facts whose SUBJECTS are this similar are treated as the same slot, so the
    # newer one supersedes instead of both persisting ("birthday_month" vs "birthday
    # month"). Measured cosines on bge-small: birthday_month/birthday month 0.953,
    # dog's name/pet_name 0.903 — but sister's name/brother's name is 0.822 and MUST
    # NOT merge, so the bar sits above that. Deliberately conservative: a missed merge
    # leaves a harmless duplicate, a wrong merge destroys a real fact.
    dedupe_subject_similarity: float = 0.88
    debug_extraction: bool = False       # print the exchange + raw LLM output + parse result
                                        # each extraction (temporary, for trust/debugging)


@dataclass(frozen=True)
class ScheduleConfig:
    tick_seconds: float = 2.0            # how often due reminders are checked
    stale_after_minutes: int = 120       # older than this overdue -> dropped, not announced
    overdue_note_after_seconds: int = 60  # later than this -> she admits how late it is


@dataclass(frozen=True)
class KnowledgeConfig:
    """What she has read. `python -m isha learn <name> <path>` fills it."""
    enabled: bool = True
    top_k: int = 2                       # passages considered per turn
    chunk_chars: int = 800               # ~200 tokens; two of them still fit num_ctx
    char_budget: int = 1200              # hard cap on what gets injected in one turn
    # Cosine DISTANCE gate. Above this, the closest passage is not actually about what
    # he said, and injecting it would drag a document into a conversation about his day.
    # MEASURED on bge-small against a real ingested document: eight genuine questions
    # about it landed 0.182-0.446, eight ordinary utterances 0.478-0.586. The gate sits
    # just inside that gap. The margin is thin (0.032), and on a wider corpus the two
    # clusters will overlap — when they do, move this DOWN. A missed retrieval is a
    # question she answers without the document; a false one puts a paragraph about
    # guitar strings into a conversation about his day.
    max_distance: float = 0.46


def _default_apps() -> dict[str, str]:
    """What "open X" is allowed to reach. Add a line here to teach her a new one — a
    protocol URL, an exe on PATH, a full path, a folder, or a website.

    A registry rather than "whatever he named": an open list would mean guessing at an
    executable name from speech, and a wrong guess either does nothing or starts
    something he didn't ask for. A miss here is recoverable — she says she doesn't have
    that one and he adds it."""
    home = Path.home()
    return {
        "spotify": "spotify:",
        "chrome": "chrome",
        "edge": "msedge",
        "firefox": "firefox",
        "notepad": "notepad",
        "calculator": "calc",
        "paint": "mspaint",
        "explorer": str(home),
        "files": str(home),
        "file explorer": str(home),
        "downloads": str(home / "Downloads"),
        "documents": str(home / "Documents"),
        "desktop": str(home / "Desktop"),
        "code": "code",
        "vs code": "code",
        "vscode": "code",
        "terminal": "wt",
        "task manager": "taskmgr",
        "settings": "ms-settings:",
        "youtube": "https://www.youtube.com",
        "github": "https://github.com",
        "gmail": "https://mail.google.com",
        "maps": "https://maps.google.com",
    }


@dataclass(frozen=True)
class ActionsConfig:
    enabled: bool = True
    apps: dict[str, str] = field(default_factory=_default_apps)
    # Where "find my ..." looks. Deliberately a short list of his own folders, not the
    # whole drive: a full walk stalls the turn and turns up program files, not his work.
    search_roots: tuple[Path, ...] = field(default_factory=lambda: (
        Path.home() / "Documents", Path.home() / "Desktop", Path.home() / "Downloads",
    ))
    search_limit: int = 5                # most results she will read out
    search_max_depth: int = 4            # folders deep from each root


@dataclass(frozen=True)
class Config:
    reasoning: ReasoningConfig = field(default_factory=ReasoningConfig)
    speech: SpeechConfig = field(default_factory=SpeechConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    wake: WakeConfig = field(default_factory=WakeConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    actions: ActionsConfig = field(default_factory=ActionsConfig)
    knowledge: KnowledgeConfig = field(default_factory=KnowledgeConfig)


CONFIG = Config()
