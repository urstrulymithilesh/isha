# Isha

A **fully-local, offline voice AI partner**. No cloud APIs, no cloud costs, no
data ever leaves the machine. Say a wake word, talk to her, and she replies in
voice — and she *remembers* you across sessions.

Built as a portfolio project under a real constraint: a laptop with a **GTX 1050
(4GB VRAM)**. That constraint drives every architecture decision, and the whole
thing is designed so a future GPU upgrade means swapping a bigger model behind a
clean interface — not a rewrite.

> Full design + engineering-review record: **[DESIGN.md](DESIGN.md)**.

## Architecture at a glance

```
  AudioTransport → WakeWord → Transcriber → LLM → Synthesizer → AudioTransport
   (WASAPI mic)    (openWW)   (whisper CPU) (llama3  (Piper CPU)    (headset out)
                                            GPU)
                         │                    │
                    Orchestrator (asyncio) ── MemoryStore (SQLite + sqlite-vec)
                    preemption state machine   async idle-gap fact extraction
                    Scheduler (SQLite-persisted timers & reminders)
```

**Compute split:** GPU does reasoning only (the model stays resident). CPU hears (faster-whisper
int8), speaks (Piper), and embeds. Nothing contends for the 4GB.

**Stack (all free / local):** Ollama + llama3.2 · faster-whisper · Piper ·
openWakeWord + Silero VAD · SQLite + sqlite-vec · custom asyncio orchestrator.

## Status

Working end to end, offline:

- **Voice loop** — wake word -> speech-to-text -> local LLM -> speech, on a custom
  asyncio preemption state machine (idle / listening / thinking / speaking) with
  stop-word barge-in and half-duplex mic gating.
- **Memory** — SQLite + `sqlite-vec` semantic recall with CPU embeddings. Facts are
  extracted in the idle gap after a reply and survive restarts; an interrupted
  extraction is retried on next start rather than lost.
- **Personality** — a warm, opinionated persona (not an assistant voice), plus seeded
  identity facts that conversational extraction cannot overwrite.
- **Self-awareness** — she can describe her current build, and her mood tracks
  whether real progress was made since the last version.
- **Timers and reminders** — "set a timer for 10 minutes", "remind me to stretch at
  5pm". Parsed deterministically (no extra model round-trip), stored with an absolute
  wall-clock time, and reconciled on wake — so a reminder survives the laptop sleeping
  or the app restarting, and admits it if it ends up late.

- **Doing things on the computer** — "open Spotify", "next track", "find my tax notes".
  Also deterministic, against a registry of things she is allowed to open (edit
  `CONFIG.actions.apps` to teach her a new one). She reports what actually happened,
  so a failed open is admitted rather than confirmed. Deleting, moving and running
  arbitrary scripts are deliberately excluded.

- **Things she has read** — `python -m isha learn guitar ./notes/guitar.md`. Documents
  are chunked, embedded, and retrieved when he *names the subject* (in that sentence or
  a recent turn), so a corpus never barges into small talk. If his words merely brush a
  document's own vocabulary, she asks — "Are you asking about your guitar?" — and a yes
  gets the answer. She answers from the passages or says they don't cover it — right
  about five times in six, which is the honest number, not a solved problem.

- **Reading her own sources** (off by default) — `python -m isha digest --fetch`, or
  on a 6-hourly schedule once `CONFIG.digest.enabled` is on. RSS/Atom feeds only, no
  web scraping. She never brings it up unprompted; ask "anything new?" and she tells
  you what actually came in, or says nothing has. This is the only part of Isha that
  touches the network, which is why it ships switched off.

Deferred: GPU acceleration (Ollama's Vulkan discovery times out on this GTX 1050, so
the LLM runs ~12 tok/s on CPU), a custom wake word, and voice cloning.

## Setup

Python **3.11-3.13** (3.13.2 is what this is developed on; every wheel resolves).
You also need [Ollama](https://ollama.com) installed and running.

```bash
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
ollama pull llama3.2
# Her voice (~60MB, offline after this):
python -m piper.download_voices en_US-amy-medium --download-dir models
# Her ears — the wake-word models (~10MB, offline after this):
python -c "import openwakeword.utils as u; u.download_models()"
```

Those three downloads are the only time Isha touches the network. After them she
runs entirely offline — pull your ethernet cable and she still works.

> **Note:** the wake-word models install *inside* the virtualenv, so if you ever
> delete and rebuild `.venv` you need to re-run that last command. `python spike.py`
> checks for them and tells you if they're missing.

Then talk to her:

```bash
python -m isha run --ollama          # add --device N to pick a specific mic
```

Useful extras: `python -m isha memory` (inspect what she remembers),
`python -m isha devices` (list mics), `python -m isha say "text"` (test her voice).

## Verify your setup (the spike)

Proves the hardware round-trip and clears the Windows install landmines. It runs
even before you've installed everything — it reports what's missing.

```bash
python spike.py                    # probe everything
python spike.py path\to\clip.wav   # also time STT on a real 16kHz mono wav
```

Green = go. A red probe (e.g. sqlite-vec won't load) blocks app code.

## Run the tests

Two layers, deliberately:

```bash
.venv\Scripts\python.exe -m pytest        # 365 unit tests with fakes, ~2 seconds
.venv\Scripts\python.exe -m isha smoke    # 8 scenarios on the REAL stack, ~3 minutes
```

(If you have run `.venv\Scriptsctivate`, plain `pytest` and `python -m isha smoke`
work too. Running them with the *system* Python fails on a missing dependency —
`isha` will tell you so and point at the venv rather than dumping a traceback.)

The unit tests drive the orchestrator with fakes — a stateless wake detector, an
instant LLM — so they pin logic fast. But a fake can only fail in ways you thought
to model, and the serious bugs here were all outside that: a brain failure swallowed
inside a worker thread, a real wake detector going deaf after a long reply because it
needs continuous audio, and the wake word bleeding into the transcript and breaking
fact extraction. None were reachable with fakes.

`isha smoke` runs the real Ollama, Piper, faster-whisper and SQLite end to end, using
Piper as a mouth feeding the pipeline's ears — so it needs no microphone, no speakers
and no human. It covers a conversation turn, memory stored and recalled across a new
connection, a spoken timer firing, barge-in, the wake word still working after a long
reply, an app she does not have being admitted rather than agreed to, a document being
ingested and answered from, and a feed being read and reported honestly. Each scenario
uses a temporary database; your real memory is untouched.

Run the unit tests constantly; run the smoke test after anything that touches audio,
threading, or the model boundary.


## Privacy

Everything runs on-device and offline. Runtime data (`data/`, `*.db`, `*.wav`,
`models/`) is gitignored and never leaves your machine.

The one exception is opt-in and off by default: with `CONFIG.digest.enabled` switched
on she fetches the RSS feeds you list. Those are plain GETs for public feeds — no
conversation, no memory, no identifier beyond a user agent — but they are outbound
traffic, so the "never touches the network" claim holds only while this is off.

## License note (TTS is GPL-3.0)

Isha's own code is MIT (see `pyproject.toml`). The TTS engine, **piper-tts**
(OHF-Voice/piper1-gpl), is **GPL-3.0** — the old MIT `rhasspy/piper` is archived.

What that means in practice for this repo:

- We depend on piper-tts via `requirements.txt` and call its Python API; we do
  **not** copy or redistribute its source or the voice model (`models/` is
  gitignored). A source-only project that lists a GPL package as a dependency and
  lets users `pip install` it themselves does not, in common practice, force the
  rest of the repo to become GPL.
- The GPL obligations (offer source, license the combined work under GPL) bite if
  you **distribute a bundled/combined work** — e.g. ship a single installer or
  frozen `.exe` that includes piper-tts. If you go that route, plan to comply or
  swap the TTS backend.
- Because TTS sits behind the `Synthesizer` interface, swapping to a
  permissively-licensed engine later is a one-file change — you're not locked in.

Not legal advice; just the honest lay of the land for a portfolio repo.
