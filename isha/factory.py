"""Builds a live Orchestrator from CONFIG. THIS is the swap point.

Change one line here (or just install the Piper binary / flip use_ollama) and the
whole pipeline upgrades — no orchestrator or interface changes. That is the payoff
of coding to the contracts in isha/core/interfaces.py.
"""

from __future__ import annotations

from isha.core.state import ConversationState
from isha.persona import SYSTEM_PROMPT


def _print_state(state: ConversationState) -> None:
    print(f"  [state] -> {state.value}")


def build_orchestrator(*, use_ollama: bool = False, input_device: int | None = None):
    """Returns (orchestrator, voice_label, brain_label). input_device overrides
    CONFIG.audio.input_device (from `run --device N`)."""
    from isha.audio.transport import LocalAudioTransport
    from isha.audio.vad import EnergyVad
    from isha.audio.wakeword import OpenWakeWordDetector
    from isha.config import CONFIG
    from isha.llm.echo import EchoLLM
    from isha.orchestrator import Orchestrator
    from isha.stt.whisper import WhisperTranscriber
    from isha.tts.piper import PiperSynthesizer
    from isha.tts.stub import StubSynthesizer

    in_dev = input_device if input_device is not None else CONFIG.audio.input_device
    transport = LocalAudioTransport(
        input_device=in_dev, output_device=CONFIG.audio.output_device,
        gain=CONFIG.audio.capture_gain,
    )
    wake = OpenWakeWordDetector(CONFIG.wake.model)
    stopword = OpenWakeWordDetector(CONFIG.wake.stop_word)
    vad = EnergyVad(
        threshold=CONFIG.audio.vad_threshold,
        silence_ms=CONFIG.audio.vad_silence_ms,
        min_speech_ms=CONFIG.audio.vad_min_speech_ms,
    )
    transcriber = WhisperTranscriber()

    if PiperSynthesizer.is_available():
        synthesizer = PiperSynthesizer()
        voice_label = f"Piper ({CONFIG.speech.piper_voice})"
    else:
        synthesizer = StubSynthesizer()
        voice_label = "STUB (install the Piper binary to swap in real speech)"

    # Memory needs a real brain to extract facts, so it's wired only with Ollama.
    store = None
    extractor = None
    if use_ollama:
        from isha.llm.ollama import OllamaLLM
        from isha.memory.embedder import FastEmbedEmbedder
        from isha.memory.extraction import FactExtractor
        from isha.memory.store import SqliteMemoryStore
        llm = OllamaLLM()
        brain_label = f"Ollama/{CONFIG.reasoning.model}"
        CONFIG.memory.db_path.parent.mkdir(parents=True, exist_ok=True)
        store = SqliteMemoryStore(
            CONFIG.memory.db_path, FastEmbedEmbedder(),
            log_path=CONFIG.memory.db_path.parent / "memory-log.txt",
        )
        from isha.schedule.scheduler import Scheduler
        from isha.schedule.store import SqliteScheduleStore
        from isha.memory.seed import seed_if_needed
        n = seed_if_needed(store)      # first run: plant core + self facts
        if n:
            print(f"  [memory] seeded {n} core/self facts (first run)")
        extractor = FactExtractor(llm)
        schedule_store = SqliteScheduleStore(CONFIG.memory.db_path)
    else:
        llm = EchoLLM()
        brain_label = "Echo (Phase 0 stub brain)"

    from isha.audio.frames import ms_to_chunks
    orch = Orchestrator(
        transport=transport, wake=wake, stopword=stopword, vad=vad,
        transcriber=transcriber, llm=llm, synthesizer=synthesizer,
        system_prompt=SYSTEM_PROMPT, preroll_frames=ms_to_chunks(CONFIG.audio.preroll_ms),
        store=store, extractor=extractor, on_state_change=_print_state,
    )
    # Scheduler needs the orchestrator's notify(), so it's attached after construction.
    if use_ollama:
        orch.scheduler = Scheduler(
            schedule_store, orch.notify,
            tick_seconds=CONFIG.schedule.tick_seconds,
            stale_after_s=CONFIG.schedule.stale_after_minutes * 60,
            overdue_note_after_s=CONFIG.schedule.overdue_note_after_seconds,
        )
    return orch, voice_label, brain_label
