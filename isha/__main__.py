"""Entry point.

    python -m isha              # status
    python -m isha --spike      # hardware + plumbing spike
    python -m isha run          # run the live walking-skeleton loop (needs mic + models)
    python -m isha run --ollama # same, but use the real Ollama brain instead of Echo
"""

from __future__ import annotations

import asyncio
import sys

from isha import __version__
from isha.config import CONFIG


def _status() -> int:
    print(f"Isha v{__version__} — fully-local voice companion")
    print(f"  reasoning : {CONFIG.reasoning.model} via {CONFIG.reasoning.ollama_host}")
    print(f"  stt       : faster-whisper {CONFIG.speech.whisper_model} ({CONFIG.speech.whisper_compute_type}, CPU)")
    print(f"  wake/stop : {CONFIG.wake.model} / {CONFIG.wake.stop_word}")
    print(f"  memory    : {CONFIG.memory.db_path}")
    print()
    print("Commands:  python -m isha run     (live loop)")
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

        python -m isha memory                 # list every stored fact
        python -m isha memory "my sister"     # semantic recall for a query
    """
    from isha.memory.embedder import FastEmbedEmbedder
    from isha.memory.store import SqliteMemoryStore

    db = CONFIG.memory.db_path
    if not db.exists():
        print(f"No memory yet at {db}.")
        print("Talk to Isha with `python -m isha run --ollama` first so she can store things.")
        return 0

    store = SqliteMemoryStore(db, FastEmbedEmbedder())
    query = " ".join(a for a in argv if not a.startswith("--")).strip()
    if query:
        hits = store.recall(query, k=CONFIG.memory.recall_k)
        print(f"Recall for {query!r} (top {CONFIG.memory.recall_k}):")
        for f in hits:
            print(f"  - [{f.subject}] {f.text}  (conf {f.confidence})")
        if not hits:
            print("  (nothing relevant found)")
    else:
        facts = store.all_facts()
        print(f"{len(facts)} fact(s) stored in {db}:")
        for f in facts:
            print(f"  - [{f.subject}] {f.text}  (conf {f.confidence})")
    print(f"\nMemory log: {db.parent / 'memory-log.txt'}")
    store.close()
    return 0


def _run(argv: list[str]) -> int:
    from isha.audio.calibrate import calibrate
    from isha.audio.devices import DeviceError

    from isha.factory import build_orchestrator

    device = _device_arg(argv)
    orch, voice_label, brain_label = build_orchestrator(
        use_ollama="--ollama" in argv, input_device=device,
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
    if argv and argv[0] == "run":
        return _run(argv[1:])
    return _status()


if __name__ == "__main__":
    raise SystemExit(main())
