"""Entry point.

    python -m isha              # status
    python -m isha --spike      # hardware + plumbing spike
    python -m isha run          # run the live walking-skeleton loop (needs mic + models)
    python -m isha run --ollama # same, but use the real Ollama brain instead of Echo
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from isha import __version__
from isha.config import CONFIG


def _status() -> int:
    print(f"Isha v{__version__} — fully-local voice partner")
    print(f"  reasoning : {CONFIG.reasoning.model} via {CONFIG.reasoning.ollama_host}")
    print(f"  stt       : faster-whisper {CONFIG.speech.whisper_model} ({CONFIG.speech.whisper_compute_type}, CPU)")
    print(f"  wake/stop : {CONFIG.wake.model} / {CONFIG.wake.stop_word}")
    print(f"  memory    : {CONFIG.memory.db_path}")
    print()
    print("Commands:  python -m isha run     (live loop)")
    print("           python -m isha smoke   (live end-to-end check, ~1-3 min)")
    print("           python -m isha run --ui  (adds the text UI at 127.0.0.1:8765)")
    print("           python spike.py        (prove the hardware)")
    return 0


def _flag_value(argv: list[str], flag: str) -> str | None:
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def _device_arg(argv: list[str]) -> int | None:
    v = _flag_value(argv, "--device")
    return int(v) if v is not None else None


def _effective_device(device: int | None) -> int | None:
    return device if device is not None else CONFIG.audio.input_device


def _calibrate_cmd(argv: list[str]) -> int:
    """Standalone: measure the mic and print config values to paste in."""
    from isha.audio.calibrate import calibrate
    from isha.audio.devices import DeviceError, validate_input_device

    device = _effective_device(_device_arg(argv))
    try:
        validate_input_device(device)
        result = calibrate(device)
    except DeviceError as e:
        print(f"\n{e}")
        return 1
    print("\n  Put these in isha/config.py -> AudioConfig to make them permanent:")
    print(f"      capture_gain: float = {result.gain}")
    print(f"      vad_threshold: float = {result.threshold}")
    if not result.ok:
        print("  (calibration was not confident — see the message above)")
    return 0


def _say_cmd(argv: list[str]) -> int:
    """Synthesize text to a wav with a chosen voice — for A/B-ing voices offline.

        python -m isha say "hello there" --voice en_US-amy-medium
    """
    import wave

    from isha.tts.piper import PiperSynthesizer, _voice_model_path

    voice = _flag_value(argv, "--voice") or CONFIG.speech.piper_voice
    words, skip = [], False
    for a in argv:
        if a == "--voice":
            skip = True
            continue
        if skip:
            skip = False
            continue
        words.append(a)
    text = " ".join(words) or "Hey you, good to hear your voice. What's going on today?"

    if not _voice_model_path(voice).is_file():
        print(f"Voice '{voice}' isn't downloaded yet. Get it with:")
        print(f"  python -m piper.download_voices {voice} --download-dir models")
        return 1

    synth = PiperSynthesizer(voice=voice)
    pcm = bytearray()
    for chunk in synth.synthesize(text):
        pcm.extend(chunk)
    out = f"say_{voice}.wav"
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(synth.sample_rate)
        w.writeframes(bytes(pcm))
    print(f"Wrote {out} ({len(pcm)/2/synth.sample_rate:.1f}s @ {synth.sample_rate}Hz)")
    print(f"Play it:  Start-Process .\\{out}")
    return 0


def _memory_cmd(argv: list[str]) -> int:
    """Inspect what Isha has stored (trust/debug).

        python -m isha memory                      # list every stored fact
        python -m isha memory "my sister"          # semantic recall for a query
        python -m isha memory --forget "Pune"      # delete facts matching that text
        python -m isha memory --dedupe             # PREVIEW near-duplicate merges
        python -m isha memory --dedupe --apply     # actually merge them
    """
    from isha.memory.embedder import FastEmbedEmbedder
    from isha.memory.store import SqliteMemoryStore

    db = CONFIG.memory.db_path
    if not db.exists():
        print(f"No memory yet at {db}.")
        print("Talk to Isha with `python -m isha run --ollama` first so she can store things.")
        return 0

    store = SqliteMemoryStore(db, FastEmbedEmbedder(),
                              log_path=db.parent / "memory-log.txt")
    if "--dedupe" in argv:
        groups = store.duplicate_groups()
        if not groups:
            print("No near-duplicate subjects found — nothing to merge.")
            store.close()
            return 0
        total = sum(len(d) for _k, d in groups)
        apply = "--apply" in argv or "--confirm" in argv
        print(f"{'MERGING' if apply else 'WOULD MERGE'} {total} fact(s) into "
              f"{len(groups)} kept fact(s):\n")
        for keeper, dups in groups:
            print(f"  KEEP    ({keeper.origin}) [{keeper.subject}] {keeper.text}")
            for dup, similarity in dups:
                print(f"  MERGE   ({dup.origin}) [{dup.subject}] {dup.text}")
                print(f"          ^ subject similarity {similarity:.3f} "
                      f"(threshold {CONFIG.memory.dedupe_subject_similarity})")
            print()
        if not apply:
            print("Preview only — nothing was changed.")
            print("Re-run with --apply to merge:  python -m isha memory --dedupe --apply")
        else:
            removed = store.merge_duplicates()
            print(f"Merged away {removed} fact(s). Logged to memory-log.txt.")
        store.close()
        return 0

    if "--forget" in argv:
        needle = " ".join(argv[argv.index("--forget") + 1:]).strip()
        if not needle:
            print('Usage: python -m isha memory --forget "some text or subject"')
            store.close()
            return 1
        gone = store.forget(needle)
        if not gone:
            print(f"Nothing matched {needle!r} — nothing deleted.")
        else:
            print(f"Forgot {len(gone)} fact(s) matching {needle!r}:")
            for f in gone:
                print(f"  - ({f.origin}) [{f.subject}] {f.text}")
            if any(f.origin in ("core", "self", "self_history") for f in gone):
                print("\nNote: some were seeded facts — `python -m isha seed` restores those.")
        store.close()
        return 0

    query = " ".join(a for a in argv if not a.startswith("--")).strip()
    if query:
        hits = store.recall(query, k=CONFIG.memory.recall_k)
        print(f"Recall for {query!r} (top {CONFIG.memory.recall_k}):")
        for f in hits:
            print(f"  - ({f.origin}) [{f.subject}] {f.text}  (conf {f.confidence})")
        if not hits:
            print("  (nothing relevant found)")
    else:
        facts = store.all_facts()
        print(f"{len(facts)} fact(s) stored in {db}:")
        for f in facts:
            print(f"  - ({f.origin}) [{f.subject}] {f.text}  (conf {f.confidence})")
    print(f"\nMemory log: {db.parent / 'memory-log.txt'}")
    store.close()
    return 0


def _seed_cmd(argv: list[str]) -> int:
    """(Re)apply the seed facts from isha/memory/seed.py — core identity/relationship +
    self build facts. Idempotent; run it once, or again after editing seed.py."""
    from isha.memory.embedder import FastEmbedEmbedder
    from isha.memory.seed import seed
    from isha.memory.store import SqliteMemoryStore

    CONFIG.memory.db_path.parent.mkdir(parents=True, exist_ok=True)
    store = SqliteMemoryStore(
        CONFIG.memory.db_path, FastEmbedEmbedder(),
        log_path=CONFIG.memory.db_path.parent / "memory-log.txt",
    )
    n = seed(store)
    print(f"Seeded/updated {n} core + self facts into {CONFIG.memory.db_path}.")
    store.close()
    return 0


def _learn_cmd(argv: list[str]) -> int:
    """Give her something to read, and see what she has read.

        python -m isha learn guitar ./docs/guitar.md   # ingest a file or a folder
        python -m isha learn --list                    # what she has learned
        python -m isha learn --forget guitar           # drop that corpus entirely
        python -m isha learn --ask "how do I tune it"  # what she'd retrieve, and how close
    """
    from isha.memory.corpus import CorpusStore
    from isha.memory.embedder import FastEmbedEmbedder

    CONFIG.memory.db_path.parent.mkdir(parents=True, exist_ok=True)
    store = CorpusStore(CONFIG.memory.db_path, FastEmbedEmbedder())

    def summary() -> None:
        corpora = store.corpora()
        if not corpora:
            print("She hasn't read anything yet.")
            return
        print("She has read:")
        for name, chunks, sources in corpora:
            print(f"  {name:20} {chunks:4} passage(s) from {sources} file(s)")

    if "--list" in argv or not argv:
        summary()
        store.close()
        return 0

    if "--forget" in argv:
        rest = argv[argv.index("--forget") + 1:]
        if not rest:
            print("Which one? e.g. python -m isha learn --forget guitar")
            store.close()
            return 2
        gone = store.forget(rest[0])
        print(f"Forgot {gone} passage(s) from {rest[0]!r}." if gone
              else f"Nothing stored under {rest[0]!r}.")
        store.close()
        return 0

    if "--ask" in argv:
        rest = argv[argv.index("--ask") + 1:]
        if not rest:
            print('Ask what? e.g. python -m isha learn --ask "how do I tune it"')
            store.close()
            return 2
        # No distance gate here on purpose: this is the tool for CHOOSING the gate, so
        # it has to show the near misses too.
        for p in store.search(rest[0], k=CONFIG.knowledge.top_k):
            marker = "USED " if p.distance <= CONFIG.knowledge.max_distance else "below"
            print(f"  [{marker} d={p.distance:.3f}] ({p.corpus}/{p.source}) "
                  f"{p.text[:160]}...")
        print(f"\nGate is {CONFIG.knowledge.max_distance} (config.knowledge.max_distance).")
        store.close()
        return 0

    if len(argv) < 2:
        print("Usage: python -m isha learn <name> <file-or-folder>")
        store.close()
        return 2
    name, path = argv[0], Path(argv[1])
    if not path.exists():
        print(f"No such file or folder: {path}")
        store.close()
        return 2
    stored = store.ingest(name, path, chunk_chars=CONFIG.knowledge.chunk_chars)
    if not stored:
        print(f"Nothing readable in {path} (looking for .txt, .md, .markdown, .rst).")
    else:
        print(f"Read {stored} passage(s) into {name!r}.")
    summary()
    store.close()
    return 0


def _run(argv: list[str]) -> int:
    from isha.audio.calibrate import calibrate
    from isha.audio.devices import DeviceError

    from isha.factory import build_orchestrator

    device = _device_arg(argv)
    channel = url = None
    if "--ui" in argv:
        from isha.ui.channel import TextChannel
        from isha.ui.server import start as start_ui
        channel = TextChannel()
        url = start_ui(channel, port=int(_flag_value(argv, "--port") or 8765))
    orch, voice_label, brain_label = build_orchestrator(
        use_ollama="--ollama" in argv, input_device=device, text_channel=channel,
    )

    # Gain / threshold: an explicit --gain wins; else auto-calibrate (unless off).
    gain_override = _flag_value(argv, "--gain")
    eff_device = _effective_device(device)
    try:
        if gain_override is not None:
            orch.transport.gain = float(gain_override)
        elif CONFIG.audio.auto_calibrate and "--no-calibrate" not in argv:
            result = calibrate(eff_device)
            if result.ok:
                orch.transport.gain = result.gain
                orch.vad.set_threshold(result.threshold)
    except DeviceError as e:
        print(f"\nAudio device problem:\n{e}")
        return 1

    dev_label = f"index {eff_device}" if eff_device is not None else (
        "OS default (run `python diagnose.py` to pick your mic)"
    )
    print("=" * 60)
    print(" Isha — walking skeleton (Phase 0)")
    print(f"   brain : {brain_label}")
    print(f"   voice : {voice_label}")
    print(f"   mic   : {dev_label}  (gain x{orch.transport.gain:.1f})")
    print(f"   VAD   : speech > {orch.vad.threshold:.0f} RMS, endpoint after {CONFIG.audio.vad_silence_ms}ms "
          f"silence (min speech {CONFIG.audio.vad_min_speech_ms}ms), pre-roll {CONFIG.audio.preroll_ms}ms")
    print(f"   wake  : say 'hey jarvis'  (PLACEHOLDER wake word — a custom 'Isha' word is Phase 4)")
    print("   stop  : say the stop word while she's speaking to cut her off")
    if url:
        print(f"   ui    : {url}  (type there; it joins the same conversation)")
    print("   Ctrl-C to quit.")
    print("=" * 60)

    try:
        asyncio.run(orch.run())
    except KeyboardInterrupt:
        print("\nGoodbye.")
    except DeviceError as e:
        print(f"\nAudio device problem:\n{e}")
        return 1
    return 0


def _wrong_python(missing: str) -> int:
    """A missing dependency here almost always means the system Python was used
    instead of the project venv, which is an easy copy-paste mistake and a very
    confusing traceback. Say so plainly."""
    print(f"Missing dependency: {missing}")
    print()
    print(f"This is running:  {sys.executable}")
    print("which is probably NOT the project venv.")
    print()
    print("Use the venv Python:")
    print(r"    .\.venv\Scripts\python.exe -m isha " + " ".join(sys.argv[1:] or ["run"]))
    print()
    print("Or, if the venv itself is incomplete:")
    print(r"    .\.venv\Scripts\python.exe -m pip install -r requirements.txt")
    return 1


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--spike" in argv:
        import spike
        return spike.main()
    if argv and argv[0] in ("devices", "--list-devices"):
        import diagnose
        diagnose.list_devices()
        return 0
    if argv and argv[0] == "calibrate":
        return _calibrate_cmd(argv[1:])
    if argv and argv[0] == "say":
        return _say_cmd(argv[1:])
    if argv and argv[0] == "memory":
        return _memory_cmd(argv[1:])
    if argv and argv[0] == "seed":
        return _seed_cmd(argv[1:])
    if argv and argv[0] == "learn":
        return _learn_cmd(argv[1:])
    if argv and argv[0] == "smoke":
        try:
            import isha.smoke
        except ImportError as e:
            return _wrong_python(e.name or str(e))
        return isha.smoke.main(argv[1:])
    if argv and argv[0] == "run":
        try:
            return _run(argv[1:])
        except ImportError as e:
            return _wrong_python(e.name or str(e))
    return _status()


if __name__ == "__main__":
    raise SystemExit(main())
