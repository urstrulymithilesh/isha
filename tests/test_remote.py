"""Remote access: the token, the audio seam, and the confirmation before side effects.

No network and no phone — the HTTP layer is thin by design, so what is pinned here is
everything that decides who gets in, where audio goes, and what she does before
opening something on a machine he is not sitting at.
"""

import asyncio

import pytest

from isha.audio.frames import CHUNK_SAMPLES
from isha.remote.auth import RemoteAuth, load_or_create, token_from_request
from isha.remote.transport import RemoteSource, SwitchingTransport

FRAME = b"\x01\x02" * CHUNK_SAMPLES


# -- the token ---------------------------------------------------------------


def test_a_token_is_created_once_and_reused(tmp_path):
    path = tmp_path / "t.txt"
    first = load_or_create(path)
    assert len(first) > 30                      # 256 bits, url-safe
    assert load_or_create(path) == first        # stable across restarts


def test_the_right_token_passes_and_the_wrong_one_does_not():
    auth = RemoteAuth("correct-horse")
    assert auth.check("correct-horse", "1.2.3.4")
    assert not auth.check("wrong", "1.2.3.4")
    assert not auth.check(None, "1.2.3.4")
    assert not auth.check("", "1.2.3.4")


def test_repeated_failures_lock_that_address_out():
    """Tailscale is the first lock. This is the second, so that one
    misconfiguration is not total access with nothing behind it."""
    auth = RemoteAuth("secret", lockout_after=3, lockout_seconds=60)
    for _ in range(3):
        assert not auth.check("nope", "9.9.9.9")
    assert auth.locked_out("9.9.9.9")
    # Even the CORRECT token is refused while locked out.
    assert not auth.check("secret", "9.9.9.9")
    # A different device is unaffected.
    assert auth.check("secret", "1.1.1.1")


def test_the_lockout_expires():
    auth = RemoteAuth("secret", lockout_after=2, lockout_seconds=60)
    for _ in range(2):
        auth.check("nope", "9.9.9.9", now=1000.0)
    assert auth.locked_out("9.9.9.9", now=1030.0)
    assert not auth.locked_out("9.9.9.9", now=1100.0)


def test_a_good_token_clears_the_failure_count():
    auth = RemoteAuth("secret", lockout_after=3)
    auth.check("nope", "1.1.1.1")
    auth.check("nope", "1.1.1.1")
    assert auth.check("secret", "1.1.1.1")
    auth.check("nope", "1.1.1.1")
    assert not auth.locked_out("1.1.1.1")       # counter reset by the success


class _Headers(dict):
    def get(self, k, default=None):
        return dict.get(self, k, default)


def test_the_token_comes_from_the_header_or_the_first_link():
    assert token_from_request(_Headers({"X-Isha-Token": "abc"}), "/") == "abc"
    assert token_from_request(_Headers(), "/?t=xyz") == "xyz"
    assert token_from_request(_Headers(), "/?t=xyz&since=3") == "xyz"
    assert token_from_request(_Headers(), "/") is None
    # The header wins, so a stale link cannot override a live session.
    assert token_from_request(_Headers({"X-Isha-Token": "abc"}), "/?t=xyz") == "abc"


# -- the audio seam ----------------------------------------------------------


class _FakeLocal:
    """The desk transport: a fixed number of frames, and a record of what was played."""

    def __init__(self, frames=6):
        self._frames = [FRAME] * frames
        self.played = []
        self.gain = 1.0
        self.muted = False

    async def capture(self):
        for f in self._frames:
            await asyncio.sleep(0)
            yield f

    async def play(self, frames, *, sample_rate=16000):
        self.played.append((b"".join(frames), sample_rate))

    def mute_input(self):
        self.muted = True

    def unmute_input(self):
        self.muted = False


def _drain(transport):
    async def go():
        return [f async for f in transport.capture()]
    return asyncio.run(go())


def test_the_desk_mic_is_used_when_no_phone_is_connected():
    local = _FakeLocal()
    t = SwitchingTransport(local, RemoteSource())
    assert len(_drain(t)) == 6
    assert t.frames_from_local == 6 and t.frames_from_remote == 0
    assert not t.remote_live


def test_the_phone_takes_over_and_the_desk_mic_is_ignored():
    """Exclusive, not merged: two live sources feeding one wake detector would
    interleave room noise with phone audio into a model that needs one continuous
    stream — which is how the detector was made to go deaf once before."""
    local = _FakeLocal()
    source = RemoteSource()
    source.submit(b"\x09\x09" * CHUNK_SAMPLES * 3)      # three frames from the phone
    t = SwitchingTransport(local, source)
    frames = _drain(t)
    assert t.remote_live
    assert t.frames_from_remote == 3
    assert t.frames_from_local == 0                      # desk audio discarded
    assert frames[0] == b"\x09\x09" * CHUNK_SAMPLES


def test_her_reply_goes_to_the_phone_while_it_has_the_floor():
    local = _FakeLocal()
    source = RemoteSource()
    source.submit(b"\x09\x09" * CHUNK_SAMPLES)
    t = SwitchingTransport(local, source)
    _drain(t)
    asyncio.run(t.play(iter([b"reply"]), sample_rate=22050))
    assert local.played == []                            # not into an empty room
    assert source.take_reply() == (b"reply", 22050)


def test_her_reply_goes_to_the_speakers_when_he_is_at_the_desk():
    local = _FakeLocal()
    t = SwitchingTransport(local, RemoteSource())
    asyncio.run(t.play(iter([b"reply"]), sample_rate=22050))
    assert local.played == [(b"reply", 22050)]


def test_the_phone_stops_being_the_source_once_it_goes_quiet():
    source = RemoteSource(idle_timeout=0.0)              # already stale
    source.submit(b"\x09\x09" * CHUNK_SAMPLES)
    assert not source.active
    t = SwitchingTransport(_FakeLocal(), source)
    _drain(t)
    assert t.frames_from_local == 6


def test_audio_arriving_while_she_speaks_is_dropped():
    """Half-duplex, same rule as the desk. Without it her own voice comes back in
    through the phone's speaker and trips the stop-word on her own reply."""
    source = RemoteSource()
    t = SwitchingTransport(_FakeLocal(), source)
    t.mute_input()
    source.submit(b"\x09\x09" * CHUNK_SAMPLES * 2)
    assert source.next_frame() is None
    t.unmute_input()
    source.submit(b"\x09\x09" * CHUNK_SAMPLES)
    assert source.next_frame() is not None


def test_a_phone_that_runs_ahead_is_trimmed_not_buffered():
    """Stale audio answers a question he has stopped asking."""
    source = RemoteSource(max_queued=4)
    source.submit(b"\x09\x09" * CHUNK_SAMPLES * 10)
    seen = 0
    while source.next_frame() is not None:
        seen += 1
    assert seen == 4


def test_calibration_reaches_the_real_microphone_through_the_wrapper():
    local = _FakeLocal()
    t = SwitchingTransport(local, RemoteSource())
    t.gain = 2.5
    assert local.gain == 2.5 and t.gain == 2.5


# -- confirming a side effect from the phone ---------------------------------


from isha.llm.echo import EchoLLM            # noqa: E402
from isha.orchestrator import Orchestrator   # noqa: E402


class _Silence:
    sample_rate = 16000

    def synthesize(self, text):
        yield b""


def _orch(remote_live: bool):
    # The desk transport needs at least one frame: the switching loop is driven by it,
    # so with none the handover never gets a chance to happen.
    local = _FakeLocal(frames=2)
    source = RemoteSource()
    if remote_live:
        source.submit(b"\x09\x09" * CHUNK_SAMPLES)
    transport = SwitchingTransport(local, source)
    _drain(transport)                         # settles which side has the floor
    assert transport.remote_live is remote_live
    return Orchestrator(
        transport=transport, wake=None, stopword=None, vad=None, transcriber=None,
        llm=EchoLLM(), synthesizer=_Silence())


def test_opening_something_from_the_phone_asks_first(monkeypatch):
    """Telephone-quality speech into the same deterministic parsers that already
    mishear at the desk, for the least reversible thing in the project."""
    import isha.orchestrator as o
    opened = []
    monkeypatch.setattr(o, "open_target", opened.append)

    orch = _orch(remote_live=True)
    assert asyncio.run(orch._handle_action_command("open spotify")) == ""
    assert opened == []                       # nothing happened yet
    assert "do you want me to open spotify" in orch._history[-1].content.lower()

    # ...and his yes carries it through.
    assert asyncio.run(orch._handle_action_command("yes")) is not None
    assert opened == ["spotify:"]


def test_at_the_desk_it_just_opens(monkeypatch):
    import isha.orchestrator as o
    opened = []
    monkeypatch.setattr(o, "open_target", opened.append)
    orch = _orch(remote_live=False)
    note = asyncio.run(orch._handle_action_command("open spotify"))
    assert opened == ["spotify:"] and "worked" in note


def test_an_unconfirmed_request_lapses(monkeypatch):
    """It must decay, not sit waiting to be triggered by an unrelated "sure" three
    turns later — the same failure the knowledge ask had."""
    import isha.orchestrator as o
    opened = []
    monkeypatch.setattr(o, "open_target", opened.append)

    orch = _orch(remote_live=True)
    asyncio.run(orch._handle_action_command("open spotify"))
    assert asyncio.run(orch._handle_action_command("actually never mind")) is None
    assert asyncio.run(orch._handle_action_command("yes")) is None
    assert opened == []


def test_reading_and_searching_are_not_gated(monkeypatch):
    """Reversible or read-only, so they keep full parity over the phone."""
    import isha.orchestrator as o
    monkeypatch.setattr(o, "find_files", lambda *a, **k: [])
    orch = _orch(remote_live=True)
    note = asyncio.run(orch._handle_action_command("find my tax notes"))
    assert note is not None and "NOTHING" in note


def test_confirmation_can_be_turned_off(monkeypatch):
    from dataclasses import replace
    import isha.orchestrator as o
    from isha.config import CONFIG

    opened = []
    monkeypatch.setattr(o, "open_target", opened.append)
    monkeypatch.setattr(o, "CONFIG",
                        replace(CONFIG, remote=replace(CONFIG.remote, confirm_actions=False)))
    orch = _orch(remote_live=True)
    asyncio.run(orch._handle_action_command("open spotify"))
    assert opened == ["spotify:"]


def test_going_quiet_while_she_speaks_does_not_hand_the_floor_back():
    """The page stops uploading during her reply — that IS the half-duplex rule. An
    idle timeout that counts it hands the desk the floor mid-conversation and plays
    her answer into an empty room, which is exactly what the smoke run caught."""
    source = RemoteSource(idle_timeout=5.0)
    source.submit(b"\x09\x09" * CHUNK_SAMPLES)
    source.muted = True                               # she has started speaking
    source.last_seen = 0.0                            # and the reply is a long one
    assert source.active                              # quiet BECAUSE she is speaking

    # The same silence, with her NOT speaking, does mean he has gone.
    quiet = RemoteSource(idle_timeout=5.0)
    quiet.submit(b"\x09\x09" * CHUNK_SAMPLES)
    quiet.last_seen = 0.0
    assert not quiet.active


def test_unmuting_gives_the_phone_a_fresh_window():
    local = _FakeLocal()
    source = RemoteSource(idle_timeout=5.0)
    t = SwitchingTransport(local, source)
    source.submit(b"\x09\x09" * CHUNK_SAMPLES)
    source.last_seen = 0.0                            # as if it had been quiet for ages
    t.mute_input()
    t.unmute_input()
    assert source.active                              # judged from now, not from before
