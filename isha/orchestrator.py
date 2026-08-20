"""The orchestrator — Isha's always-on event loop and preemption state machine.

This is the signature engineering of the project (the reason we chose a custom
asyncio loop over a framework): the mic is consumed by ONE ingest loop, and a turn
(transcribe -> think -> speak) runs as a concurrent task so the ingest loop keeps
running DURING speech. That is what lets a stop-word barge in while Isha is talking.

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
from collections import deque
from collections.abc import Callable, Iterator

from isha.core.interfaces import (
    AudioTransport,
    LLM,
    MemoryStore,
    Message,
    Synthesizer,
    Transcriber,
    WakeWord,
)
from isha.config import CONFIG
from isha.context import build_messages
from isha.core.state import ConversationState, disposition_for
from isha.audio.frames import SAMPLE_RATE
from isha.audio.vad import Vad
from isha.memory.extraction import FactExtractor, parse_extracted_facts
from isha.reply_style import trim_reflexive_question
from isha.tts.speech_text import clean_for_speech


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
        preroll_frames: int = 0,
        store: MemoryStore | None = None,
        extractor: FactExtractor | None = None,
        on_state_change: Callable[[ConversationState], None] | None = None,
    ) -> None:
        self.transport = transport
        self.wake = wake
        self.stopword = stopword
        self.vad = vad
        self.transcriber = transcriber
        self.llm = llm
        self.synth = synthesizer
        self.store = store              # None => memory disabled (e.g. Echo brain)
        self.extractor = extractor      # None => no fact extraction
        self._on_state_change = on_state_change

        self.state = ConversationState.IDLE
        self.states_visited: list[ConversationState] = [ConversationState.IDLE]
        self._buffer = bytearray()
        # Rolling recent audio so the wake-word's detection latency doesn't eat the
        # start of the sentence — prepended to the turn buffer when we start listening.
        self._preroll: deque[bytes] = deque(maxlen=preroll_frames)
        self._interrupt = asyncio.Event()
        self._turn_task: asyncio.Task[None] | None = None
        # Overlap gating: ONE lock guards every Ollama call (reply AND extraction), so
        # they can never hit the model/CPU at the same time. Extraction runs in the idle
        # gap as a background task and is cancelled the instant a new turn begins.
        self._llm_lock = asyncio.Lock()
        self._extract_task: asyncio.Task[None] | None = None
        self._alerts: list[str] = []
        self._system_prompt = system_prompt
        self._history: list[Message] = []  # conversation turns only; persona + facts added per turn

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
        if self._extract_task is not None and not self._extract_task.done():
            try:
                await self._extract_task     # let a final idle-gap extraction finish
            except asyncio.CancelledError:
                pass

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
        self._preroll.append(frame)  # always keep the most recent audio for pre-roll
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
        # A new interaction takes priority: cancel any pending idle-gap extraction so it
        # can't compete with the coming reply. Best-effort — a lost extraction is fine.
        if self._extract_task is not None and not self._extract_task.done():
            self._extract_task.cancel()
        # Seed the turn with the pre-roll so the start of the sentence (spoken during
        # the wake word's detection latency) is included. Do NOT flush here — flushing
        # would drop exactly those queued start-of-speech frames.
        self._buffer = bytearray(b"".join(self._preroll))
        self.vad.reset()
        self._enter(ConversationState.LISTENING)

    def _start_turn(self) -> None:
        audio = bytes(self._buffer)
        self._buffer = bytearray()
        self._enter(ConversationState.THINKING)
        self._turn_task = asyncio.create_task(self._run_turn(audio))

    async def _run_turn(self, audio: bytes) -> None:
        appended_user = False
        secs = len(audio) / 2 / SAMPLE_RATE  # int16 mono @ 16k
        print(f"  [captured {secs:.1f}s of audio]")
        try:
            text = (await asyncio.to_thread(self.transcriber.transcribe, audio)).strip()
            if not text:
                print("  [transcript empty — heard no clear speech]")
                self._enter(ConversationState.IDLE)
                return
            print(f'  you: "{text}"')
            self._history.append(Message("user", text))
            appended_user = True
            facts = self.store.recall(text, k=CONFIG.memory.recall_k) if self.store else []
            if facts:
                print("  [memory] recalled " + "; ".join(f.subject or f.text[:30] for f in facts))
            messages = build_messages(
                self._system_prompt, facts, self._history,
                recent_limit=CONFIG.memory.recent_turns,
                char_budget=CONFIG.memory.context_char_budget,
            )
            reply = await self._think(messages)
            reply = trim_reflexive_question(reply, keep_rate=CONFIG.reasoning.question_keep_rate)
            self._history.append(Message("assistant", reply))
            await self._speak(reply)
            self._remember_turn(text, reply)
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

    async def _think(self, messages: list[Message]) -> str:
        # EchoLLM is instant; a real streaming LLM runs off-thread so the ingest
        # loop stays responsive. The lock guarantees a reply and a background
        # extraction never hit Ollama at the same time.
        def collect() -> str:
            return "".join(self.llm.chat(messages, stream=True)).strip()

        async with self._llm_lock:
            return await asyncio.to_thread(collect)

    # -- memory ------------------------------------------------------------

    def _remember_turn(self, user_text: str, reply: str) -> None:
        """Persist the exchange and kick idle-gap fact extraction (both no-ops if
        memory isn't wired). Called after a reply is spoken, so we're back at IDLE."""
        if self.store is None:
            return
        self.store.append_turn(Message("user", user_text))
        self.store.append_turn(Message("assistant", reply))
        if self.extractor is not None:
            exchange = f"The user said: {user_text}\nYou replied: {reply}"
            self._extract_task = asyncio.create_task(self._extract_facts(exchange))

    async def _extract_facts(self, exchange: str) -> None:
        assert self.store is not None and self.extractor is not None
        try:
            async with self._llm_lock:          # never overlaps a live reply on Ollama
                if self.state is not ConversationState.IDLE:
                    return                       # a new turn started meanwhile — skip
                raw = await asyncio.to_thread(self.extractor.extract, exchange)
            facts = parse_extracted_facts(raw, min_confidence=CONFIG.memory.min_fact_confidence)
            for fact in facts:
                self.store.add_fact(fact)        # sync CPU embed; on the loop thread
            if facts:
                print("  [memory] stored "
                      + "; ".join(f.subject or f.text[:30] for f in facts))
        except asyncio.CancelledError:
            raise                                # a new turn cancelled us — clean exit
        except Exception as e:                   # noqa: BLE001 - extraction is best-effort
            print(f"  [extraction failed] {type(e).__name__}: {e}")

    async def _speak(self, text: str) -> None:
        text = clean_for_speech(text)  # single choke-point: everything spoken is voice-shaped
        if not text:
            self._enter(ConversationState.IDLE)
            return
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
