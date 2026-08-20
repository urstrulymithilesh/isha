"""End-to-end tests of the walking-skeleton loop, driven by fakes.

The orchestrator is component-agnostic, so we can exercise the FULL state machine
(wake -> listen -> think -> speak, plus stop-word interrupt and alert timing) with
zero audio hardware and zero models. Async tests are wrapped in asyncio.run so they
need only plain pytest.
"""

from __future__ import annotations

import asyncio

from esha.audio.vad import Vad
from esha.core.interfaces import LLMError
from esha.core.state import ConversationState
from esha.llm.echo import EchoLLM
from esha.orchestrator import Orchestrator

WAKE, SPEECH, END, STOP = b"WAKE", b"speech", b"END", b"STOP"


class FakeTransport:
    def __init__(self, frames: list[bytes]):
        self._frames = frames
        self.played: list[list[bytes]] = []
        self.mute_calls: list[str] = []

    async def capture(self):
        for f in self._frames:
            await asyncio.sleep(0)
            yield f

    async def play(self, frames, *, sample_rate: int = 16000):
        chunks = []
        for c in frames:
            chunks.append(c)
            await asyncio.sleep(0)
        self.played.append(chunks)

    def mute_input(self):
        self.mute_calls.append("mute")

    def unmute_input(self):
        self.mute_calls.append("unmute")

    @property
    def spoken(self) -> list[str]:
        return [b"".join(cl).decode() for cl in self.played]


class FakeWake:
    def __init__(self, trigger: bytes):
        self._trigger = trigger

    def process(self, frame: bytes) -> bool:
        return frame == self._trigger


class FakeVad(Vad):
    def is_speech(self, frame: bytes) -> bool:
        return frame != END

    def is_endpoint(self, frame: bytes) -> bool:
        return frame == END

    def reset(self) -> None:
        pass


class FakeTranscriber:
    def transcribe(self, pcm: bytes) -> str:
        return "hello world"


class TextSynth:
    """Yields the reply text as a single chunk so tests can assert what was spoken."""

    sample_rate = 16000

    def synthesize(self, text: str):
        yield text.encode()


def _build(frames: list[bytes]) -> tuple[Orchestrator, FakeTransport]:
    transport = FakeTransport(frames)
    orch = Orchestrator(
        transport=transport, wake=FakeWake(WAKE), stopword=FakeWake(STOP),
        vad=FakeVad(), transcriber=FakeTranscriber(), llm=EchoLLM(), synthesizer=TextSynth(),
    )
    return orch, transport


# -- full loop --------------------------------------------------------------


def test_happy_path_full_loop():
    orch, transport = _build([WAKE, SPEECH, END])
    asyncio.run(orch.run())

    # visited the whole cycle and returned to idle
    seq = [s for s in orch.states_visited]
    for expected in (ConversationState.LISTENING, ConversationState.THINKING,
                     ConversationState.SPEAKING):
        assert expected in seq
    assert orch.state is ConversationState.IDLE
    # the echo brain's reply was spoken
    assert transport.spoken == ["I heard you say: hello world"]


def test_no_wake_no_turn():
    orch, transport = _build([SPEECH, SPEECH])
    asyncio.run(orch.run())
    assert orch.state is ConversationState.IDLE
    assert transport.spoken == []  # never woke, never spoke


# -- stop-word interrupt (Finding #3) --------------------------------------


def test_interruptible_stops_when_flagged():
    orch, _ = _build([])
    orch._interrupt.set()
    assert list(orch._interruptible(iter([b"a", b"b", b"c"]))) == []


def test_interruptible_passes_through_when_clear():
    orch, _ = _build([])
    assert list(orch._interruptible(iter([b"a", b"b"]))) == [b"a", b"b"]


def test_stopword_during_speaking_sets_interrupt():
    orch, _ = _build([])
    orch._enter(ConversationState.SPEAKING)
    asyncio.run(orch._handle_frame(STOP))
    assert orch._interrupt.is_set()


# -- alert timing (pending-alert overlay) ----------------------------------


def test_alert_while_idle_is_spoken_now():
    orch, transport = _build([b"x"])  # one non-wake frame
    orch.notify("your timer is done")
    asyncio.run(orch.run(max_frames=1))
    assert "your timer is done" in transport.spoken


class BrokenLLM:
    supports_tools = False

    def chat(self, messages, *, stream=True):
        raise LLMError("simulated Ollama 500")


def test_brain_failure_does_not_hang_and_speaks_error():
    orch, transport = _build([WAKE, SPEECH, END])
    orch.llm = BrokenLLM()
    asyncio.run(orch.run())
    # did not stall in THINKING/SPEAKING — recovered to idle
    assert orch.state is ConversationState.IDLE
    # spoke a clear apology instead of a reply, and left no dangling user turn
    assert transport.spoken and "went wrong" in transport.spoken[-1].lower()
    assert [m for m in orch._history if m.role == "user"] == []


def test_alert_during_listening_waits_until_after_reply():
    orch, transport = _build([])

    async def scenario():
        await orch._handle_frame(WAKE)      # -> LISTENING
        orch.notify("gym at 5pm")           # fires while user is talking
        await orch._handle_frame(SPEECH)
        await orch._handle_frame(END)       # -> starts the turn
        assert orch._turn_task is not None
        await orch._turn_task

    asyncio.run(scenario())
    # reply first, alert second — never cut the user off
    assert transport.spoken == ["I heard you say: hello world", "gym at 5pm"]
