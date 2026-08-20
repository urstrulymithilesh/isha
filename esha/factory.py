"""Builds a live Orchestrator from CONFIG. THIS is the swap point.

Change one line here (or just install the Piper binary / flip use_ollama) and the
whole pipeline upgrades — no orchestrator or interface changes. That is the payoff
of coding to the contracts in esha/core/interfaces.py.
"""

from __future__ import annotations

from esha.core.state import ConversationState
from esha.persona import SYSTEM_PROMPT


def _print_state(state: ConversationState) -> None:
    print(f"  [state] -> {state.value}")


def build_orchestrator(*, use_ollama: bool = False, input_device: int | None = None):
    """Returns (orchestrator, voice_label, brain_label). input_device overrides
    CONFIG.audio.input_device (from `run --device N`)."""
    from esha.audio.transport import LocalAudioTransport
    from esha.audio.vad import EnergyVad
    from esha.audio.wakeword import OpenWakeWordDetector
    from esha.config import CONFIG
    from esha.llm.echo import EchoLLM
    from esha.orchestrator import Orchestrator
    from esha.stt.whisper import WhisperTranscriber
    from esha.tts.piper import PiperSynthesizer
    from esha.tts.stub import StubSynthesizer

    in_dev = input_device if input_device is not None else CONFIG.audio.input_device
    transport = LocalAudioTransport(
        input_device=in_dev, output_device=CONFIG.audio.output_device,
        gain=CONFIG.audio.capture_gain,
    )
    wake = OpenWakeWordDetector(CONFIG.wake.model)
    stopword = OpenWakeWordDetector(CONFIG.wake.stop_word)
    vad = EnergyVad(threshold=CONFIG.audio.vad_threshold, silence_ms=CONFIG.audio.vad_silence_ms)
    transcriber = WhisperTranscriber()

    if PiperSynthesizer.is_available():
        synthesizer = PiperSynthesizer()
        voice_label = f"Piper ({CONFIG.speech.piper_voice})"
    else:
        synthesizer = StubSynthesizer()
        voice_label = "STUB (install the Piper binary to swap in real speech)"

    if use_ollama:
        from esha.llm.ollama import OllamaLLM
        llm = OllamaLLM()
        brain_label = f"Ollama/{CONFIG.reasoning.model}"
    else:
        llm = EchoLLM()
        brain_label = "Echo (Phase 0 stub brain)"

    orch = Orchestrator(
        transport=transport, wake=wake, stopword=stopword, vad=vad,
        transcriber=transcriber, llm=llm, synthesizer=synthesizer,
        system_prompt=SYSTEM_PROMPT, on_state_change=_print_state,
    )
    return orch, voice_label, brain_label
