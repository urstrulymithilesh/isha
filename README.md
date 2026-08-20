# Esha

A **fully-local, offline voice AI companion**. No cloud APIs, no cloud costs, no
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

## Status: Phase 0 (walking skeleton)

The interfaces and the preemption state machine are defined; the pipeline isn't
wired yet. Current step is proving the hardware + install on the real machine.

## Setup

Use **Python 3.11 or 3.12** (some ML wheels lag on 3.13).

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
ollama pull qwen2.5:3b-instruct
# Download a Piper voice (used for real speech; ~60MB, offline after this):
python -m piper.download_voices en_US-lessac-medium --download-dir models
```

## Run the Phase 0 spike (do this first)

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

Esha's own code is MIT (see `pyproject.toml`). The TTS engine, **piper-tts**
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
