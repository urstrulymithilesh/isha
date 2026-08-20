"""Builds a live Orchestrator from CONFIG. THIS is the swap point.

Change one line here (or just install the Piper binary / flip use_ollama) and the
whole pipeline upgrades — no orchestrator or interface changes. That is the payoff
of coding to the contracts in esha/core/interfaces.py.
"""

from __future__ import annotations

from esha.core.state import ConversationState

PERSONA = (
    "You are Esha, a warm, caring personal companion who lives on this computer. "
    "You speak naturally and briefly, like a close friend on a phone call. You "
    "remember what matters to the person you're talking to. Keep replies short and "
    "conversational — this is spoken aloud."
)


def _print_state(state: ConversationState) -> None:
    print(f"  [state] -> {state.value}")


def build_orchestrator(*, use_ollama: bool = False):
    """Returns (orchestrator, voice_label). voice_label says which TTS is active."""
    from esha.audio.transport import LocalAudioTransport
    from esha.audio.vad import EnergyVad
    from esha.audio.wakeword import OpenWakeWordDetector
    from esha.config import CONFIG
    from esha.llm.echo import EchoLLM
    from esha.orchestrator import Orchestrator
    from esha.stt.whisper import WhisperTranscriber
    from esha.tts.piper import PiperSynthesizer
    from esha.tts.stub import StubSynthesizer

    transport = LocalAudioTransport()
    wake = OpenWakeWordDetector(CONFIG.wake.model)
    stopword = OpenWakeWordDetector(CONFIG.wake.stop_word)
    vad = EnergyVad()
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
        system_prompt=PERSONA, on_state_change=_print_state,
    )
    return orch, voice_label, brain_label
