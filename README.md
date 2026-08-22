# Isha

A **fully-local, offline voice AI companion**. No cloud APIs, no cloud costs, no
data ever leaves the machine. Say a wake word, talk to her, and she replies in
voice — and she *remembers* you across sessions.

Built as a portfolio project under a real constraint: a laptop with a **GTX 1050
(4GB VRAM)**. That constraint drives every architecture decision, and the whole
thing is designed so a future GPU upgrade means swapping a bigger model behind a
clean interface — not a rewrite.

> Full design + engineering-review record: **[DESIGN.md](DESIGN.md)**.

## Demo

<!--
  DROP YOUR RECORDINGS IN HERE:
    1. Create a `docs/` folder in the repo root.
    2. Put the silent GIF at        docs/demo.gif   (GitHub autoplays GIFs inline)
    3. Put the MP4 with audio at    docs/demo.mp4   (linked below; GitHub won't
       autoplay a committed MP4, so it's a click-through)
    4. Delete this comment block.

  Tip: to get an MP4 that plays INLINE on GitHub, open any issue in your repo,
  drag the .mp4 into the comment box, and GitHub uploads it and gives you a
  user-images URL. Paste that URL here on its own line and it renders as a
  player. (Don't submit the issue - you only need the generated link.)
-->

![Isha: wake word, local reply, and memory that survives a restart](docs/demo.gif)

*Everything above runs on one laptop with no network: wake word, speech-to-text,
a local LLM, and a real voice.*

**[▶ Watch with audio (MP4)](docs/demo.mp4)** — her voice is half the point, and
the GIF is silent.

## Architecture at a glance

```
  AudioTransport → WakeWord → Transcriber → LLM → Synthesizer → AudioTransport
   (WASAPI mic)    (openWW)   (whisper CPU) (Qwen  (Piper CPU)    (headset out)
                                            GPU)
                         │                    │
                    Orchestrator (asyncio) ── MemoryStore (SQLite + sqlite-vec)
                    preemption state machine   async idle-gap fact extraction
                    Scheduler (SQLite-persisted timers & reminders)
```

**Compute split:** GPU does reasoning only (Qwen resident). CPU hears (faster-whisper
int8), speaks (Piper), and embeds. Nothing contends for the 4GB.

**Stack (all free / local):** Ollama + Qwen2.5-3B · faster-whisper · Piper ·
openWakeWord + Silero VAD · SQLite + sqlite-vec · custom asyncio orchestrator.

## Status

Working end to end, offline:

- **Voice loop** — wake word -> speech-to-text -> local LLM -> speech, on a custom
  asyncio preemption state machine (idle / listening / thinking / speaking) with
  stop-word barge-in and half-duplex mic gating.
- **Memory** — SQLite + `sqlite-vec` semantic recall with CPU embeddings. Facts are
  extracted in the idle gap after a reply and survive restarts; an interrupted
  extraction is retried on next start rather than lost.
- **Personality** — a warm companion persona (not an assistant voice), plus seeded
  identity facts that conversational extraction cannot overwrite.
- **Self-awareness** — she can describe her current build, and her mood tracks
  whether real progress was made since the last version.
- **Timers and reminders** — "set a timer for 10 minutes", "remind me to stretch at
  5pm". Parsed deterministically (no extra model round-trip), stored with an absolute
  wall-clock time, and reconciled on wake — so a reminder survives the laptop sleeping
  or the app restarting, and admits it if it ends up late.

Deferred: GPU acceleration (Ollama's Vulkan discovery times out on this GTX 1050, so
the LLM runs ~12 tok/s on CPU), a custom wake word, and voice cloning.

## Setup

Python **3.11-3.13** (3.13.2 is what this is developed on; every wheel resolves).
You also need [Ollama](https://ollama.com) installed and running.

```bash
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
ollama pull qwen2.5:3b
# Her voice (~60MB, offline after this):
python -m piper.download_voices en_US-amy-medium --download-dir models
```

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

The deterministic core (preemption logic, and soon memory + scheduler) is
100% unit-tested with no hardware or models:

```bash
pytest
```

## Privacy

Everything runs on-device and offline. Runtime data (`data/`, `*.db`, `*.wav`,
`models/`) is gitignored and never leaves your machine.

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
