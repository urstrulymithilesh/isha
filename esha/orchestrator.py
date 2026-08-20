"""The orchestrator — Esha's always-on event loop and preemption state machine.

This is the signature engineering of the project (the reason we chose a custom
asyncio loop over a framework): the mic is consumed by ONE ingest loop, and a turn
(transcribe -> think -> speak) runs as a concurrent task so the ingest loop keeps
running DURING speech. That is what lets a stop-word barge in while Esha is talking.

    ┌──── wake ────► LISTENING ──── endpoint ────► THINKING ──── reply ────┐
   IDLE                (buffer STT)                 (LLM)                    │
    ▲                                                                       ▼
    └────────── reply done / stop-word ──────────────────────────────── SPEAKING
                                                     (Piper/stub + stop-word live)

The orchestrator is COMPONENT-AGNOSTIC: it drives injected WakeWord / Vad /
Transcriber / LLM / Synthesizer / AudioTransport objects. That is what makes the
whole machine unit-testable today with fakes, and what makes swapping the TTS stub
for Piper (or Echo for Ollama) a factory change, not a rewrite.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator

from esha.core.interfaces import (
    AudioTransport,
    LLM,
    Message,
    Synthesizer,
    Transcriber,
    WakeWord,
)
from esha.core.state import ConversationState, disposition_for
from esha.audio.vad import Vad


class Orchestrator:
    def __init__(
        self,
        *,
        transport: AudioTransport,
        wake: WakeWord,
        stopword: WakeWord,
        vad: Vad,
        transcriber: Transcriber,
        llm: LLM,
        synthesizer: Synthesizer,
        system_prompt: str = "",
        on_state_change: Callable[[ConversationState], None] | None = None,
    ) -> None:
        self.transport = transport
        self.wake = wake
        self.stopword = stopword
        self.vad = vad
        self.transcriber = transcriber
        self.llm = llm
        self.synth = synthesizer
        self._on_state_change = on_state_change

        self.state = ConversationState.IDLE
        self.states_visited: list[ConversationState] = [ConversationState.IDLE]
        self._buffer = bytearray()
        self._interrupt = asyncio.Event()
        self._turn_task: asyncio.Task[None] | None = None
        self._alerts: list[str] = []
        self._history: list[Message] = [Message("system", system_prompt)] if system_prompt else []

    # -- public ------------------------------------------------------------

    async def run(self, *, max_frames: int | None = None) -> None:
        """Consume mic frames until the transport ends (or max_frames, for tests)."""
        n = 0
        async for frame in self.transport.capture():
            await self._handle_frame(frame)
            n += 1
            if max_frames is not None and n >= max_frames:
                break
        if self._turn_task is not None:
            await self._turn_task

    def notify(self, text: str) -> None:
        """A fired timer/reminder. disposition_for() governs WHEN it's spoken;
        the queue is drained whenever we're safely back at IDLE (never cutting the
        user off mid-utterance)."""
        _ = disposition_for(self.state)  # documents intent; drain point enforces it
        self._alerts.append(text)

    # -- state transitions -------------------------------------------------

    def _enter(self, state: ConversationState) -> None:
        self.state = state
        self.states_visited.append(state)
        if self._on_state_change is not None:
            self._on_state_change(state)

    async def _handle_frame(self, frame: bytes) -> None:
        st = self.state
        if st is ConversationState.IDLE:
            if self._alerts:
                await self._speak(self._alerts.pop(0))
                return
            if self.wake.process(frame):
                self._begin_listening()
        elif st is ConversationState.LISTENING:
            self._buffer += frame
            if self.vad.is_endpoint(frame):
                self._start_turn()
        elif st is ConversationState.SPEAKING:
            # Half-duplex: full STT is gated, but the stop-word stays live.
            if self.stopword.process(frame):
                self._interrupt.set()
        # THINKING: transient; frames are ignored while the LLM runs.

    def _begin_listening(self) -> None:
        self.transport.unmute_input()  # ensure mic open + flushed
        self._buffer = bytearray()
        self.vad.reset()
        self._enter(ConversationState.LISTENING)

    def _start_turn(self) -> None:
        audio = bytes(self._buffer)
        self._buffer = bytearray()
        self._enter(ConversationState.THINKING)
        self._turn_task = asyncio.create_task(self._run_turn(audio))

    async def _run_turn(self, audio: bytes) -> None:
        appended_user = False
        try:
            text = (await asyncio.to_thread(self.transcriber.transcribe, audio)).strip()
            if not text:
                self._enter(ConversationState.IDLE)
                return
            print(f'  you: "{text}"')
            self._history.append(Message("user", text))
            appended_user = True
            reply = await self._think()
            self._history.append(Message("assistant", reply))
            await self._speak(reply)
        except Exception as e:  # noqa: BLE001 - a failed turn must never hang "thinking"
            # LLMError, TTS failure, transcription error — surface it, don't stall.
            print(f"  [turn failed] {type(e).__name__}: {e}")
            if appended_user and self._history and self._history[-1].role == "user":
                self._history.pop()  # don't leave a dangling half-exchange in context
            try:
                await self._speak("Sorry, something went wrong on my end. Let's try again.")
            except Exception:  # noqa: BLE001 - even the apology's audio can fail
                pass
        finally:
            if self.state is not ConversationState.IDLE:
                self._enter(ConversationState.IDLE)
            await self._drain_alerts()

    async def _think(self) -> str:
        # EchoLLM is instant; a real streaming LLM runs off-thread so the ingest
        # loop stays responsive. (Streaming reply -> streaming TTS is a Phase 1 tie-in.)
        def collect() -> str:
            return "".join(self.llm.chat(self._history, stream=True)).strip()

        return await asyncio.to_thread(collect)

    async def _speak(self, text: str) -> None:
        self._enter(ConversationState.SPEAKING)
        self._interrupt.clear()
        self.transport.mute_input()
        try:
            await self.transport.play(
                self._interruptible(self.synth.synthesize(text)),
                sample_rate=self.synth.sample_rate,
            )
        finally:
            self.transport.unmute_input()  # flush self-echo tail
            self._enter(ConversationState.IDLE)

    def _interruptible(self, frames: Iterator[bytes]) -> Iterator[bytes]:
        """Wrap the synth stream so a stop-word (which sets _interrupt from the
        ingest loop) cuts playback at the next frame boundary."""
        for chunk in frames:
            if self._interrupt.is_set():
                return
            yield chunk

    async def _drain_alerts(self) -> None:
        while self._alerts and self.state is ConversationState.IDLE:
            await self._speak(self._alerts.pop(0))
