"""Action parsing and file search — pure, no apps launched, no keys pressed.

The orchestrator wiring is covered at the end with fakes, the same way the scheduler is.
"""

import pytest

from isha.actions.parse import (FindCommand, MediaCommand, OpenCommand, UnknownTarget,
                                parse_action_command)
from isha.actions.run import find_files

APPS = {"spotify": "spotify:", "chrome": "chrome", "downloads": r"C:\Users\x\Downloads"}


def parse(text):
    return parse_action_command(text, APPS)


# -- opening ----------------------------------------------------------------


@pytest.mark.parametrize("said", [
    "open Spotify",
    "Open spotify.",
    "could you open Spotify",
    "launch spotify",
    "fire up Spotify please",
    "open the spotify app",
])
def test_open_phrasings(said):
    cmd = parse(said)
    assert isinstance(cmd, OpenCommand) and cmd.target == "spotify:"


def test_unknown_app_is_a_command_not_a_shrug():
    """Falling through to chat would have her agree she opened something she can't."""
    cmd = parse("open Photoshop")
    assert isinstance(cmd, UnknownTarget) and cmd.name == "photoshop"


def test_open_a_folder_from_the_registry():
    assert isinstance(parse("open my downloads"), OpenCommand)


# -- media ------------------------------------------------------------------


@pytest.mark.parametrize("said,action", [
    ("pause", "play_pause"),
    ("play", "play_pause"),
    ("pause the music", "play_pause"),
    ("stop the music", "play_pause"),
    ("next track", "next"),
    ("skip this song", "next"),
    ("previous track", "previous"),
    ("turn it up", "volume_up"),
    ("volume down", "volume_down"),
    ("mute", "mute"),
])
def test_media_phrasings(said, action):
    cmd = parse(said)
    assert isinstance(cmd, MediaCommand) and cmd.action == action


@pytest.mark.parametrize("said", [
    "we should play chess later",
    "I had to pause and think about it",
    "the next track on that album is better",
    "skip the small talk and tell me what you think",
])
def test_media_words_inside_a_sentence_are_just_talk(said):
    """Anchored at both ends on purpose: a substring rule would pause his music
    because he used the word 'pause' in a sentence, and nothing would tell him why."""
    assert parse(said) is None


# -- finding ----------------------------------------------------------------


def test_find_strips_filler_to_the_words_that_matter():
    cmd = parse("find my notes on the car")
    assert isinstance(cmd, FindCommand) and cmd.needle == "notes car"


def test_find_out_is_a_question_not_a_search():
    assert parse("find out what time the shop closes") is None


# -- bowing out -------------------------------------------------------------


@pytest.mark.parametrize("said", [
    "remind me to open Spotify at five",
    "set a timer and open chrome",
])
def test_reminder_words_belong_to_the_scheduler(said):
    assert parse(said) is None


@pytest.mark.parametrize("said", [
    "how was your day",
    "I opened the window earlier",
    "",
    "start over with what you were saying",   # too long to be a program name
    "run me through it again",                # "run" is not an open verb
])
def test_ordinary_talk_matches_nothing(said):
    assert parse(said) is None


# -- file search ------------------------------------------------------------


def test_find_files_needs_every_word(tmp_path):
    (tmp_path / "car notes.txt").write_text("x")
    (tmp_path / "car photos.txt").write_text("x")
    (tmp_path / "shopping notes.txt").write_text("x")
    hits = find_files("notes car", [tmp_path])
    assert [p.name for p in hits] == ["car notes.txt"]


def test_find_files_respects_depth_and_limit(tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "notes.txt").write_text("x")
    assert find_files("notes", [tmp_path], max_depth=1) == []
    assert len(find_files("notes", [tmp_path], max_depth=4)) == 1

    for i in range(10):
        (tmp_path / f"notes{i}.txt").write_text("x")
    assert len(find_files("notes", [tmp_path], limit=3)) == 3


def test_find_files_survives_a_missing_root(tmp_path):
    assert find_files("anything", [tmp_path / "not there"]) == []


# -- what she is told to say ------------------------------------------------
#
# The note handed to the model is the whole safety story for this feature: if it says
# "you opened it" when nothing opened, she says it too, and he stops checking.

import asyncio

from isha.actions.run import ActionError
from isha.llm.echo import EchoLLM
from isha.orchestrator import Orchestrator


class _Silence:
    sample_rate = 16000

    def synthesize(self, text: str):
        yield b""


class _NoFrames:
    async def frames(self):
        return
        yield b""       # pragma: no cover - never reached, makes this an async generator

    def play(self, pcm, sample_rate=None):
        pass

    def mute(self):
        pass

    def unmute(self):
        pass


def _orch():
    return Orchestrator(
        transport=_NoFrames(), wake=None, stopword=None, vad=None,
        transcriber=None, llm=EchoLLM(), synthesizer=_Silence(),
    )


def _note(text, monkeypatch, **patches):
    import isha.orchestrator as o
    for name, fn in patches.items():
        monkeypatch.setattr(o, name, fn)
    return asyncio.run(_orch()._handle_action_command(text))


def test_a_successful_open_is_reported_as_done(monkeypatch):
    opened = []
    note = _note("open spotify", monkeypatch, open_target=opened.append)
    assert opened == ["spotify:"]
    assert "worked" in note


def test_a_failed_open_never_claims_success(monkeypatch):
    def boom(target):
        raise ActionError("no such file")

    note = _note("open spotify", monkeypatch, open_target=boom)
    assert "did not work" in note and "Do not claim it opened" in note


def test_an_app_she_does_not_have_is_admitted(monkeypatch):
    note = _note("open photoshop", monkeypatch, open_target=lambda t: None)
    assert "did NOT open it" in note


def test_an_empty_search_forbids_inventing_a_filename(monkeypatch):
    note = _note("find my tax notes", monkeypatch, find_files=lambda *a, **k: [])
    assert "NOTHING" in note and "Do NOT invent" in note


def test_search_results_are_given_as_the_complete_list(monkeypatch):
    from pathlib import Path
    hits = [Path(r"C:\Users\x\Documents\tax") / "tax notes.txt"]
    note = _note("find my tax notes", monkeypatch, find_files=lambda *a, **k: hits)
    assert "tax notes.txt" in note and "do NOT invent any others" in note


def test_ordinary_talk_produces_no_note(monkeypatch):
    assert _note("how was your day", monkeypatch) is None
