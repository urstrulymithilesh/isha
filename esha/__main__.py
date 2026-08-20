"""Entry point.

    python -m esha              # status
    python -m esha --spike      # hardware + plumbing spike
    python -m esha run          # run the live walking-skeleton loop (needs mic + models)
    python -m esha run --ollama # same, but use the real Ollama brain instead of Echo
"""

from __future__ import annotations

import asyncio
import sys

from esha import __version__
from esha.config import CONFIG


def _status() -> int:
    print(f"Esha v{__version__} — fully-local voice companion")
    print(f"  reasoning : {CONFIG.reasoning.model} via {CONFIG.reasoning.ollama_host}")
    print(f"  stt       : faster-whisper {CONFIG.speech.whisper_model} ({CONFIG.speech.whisper_compute_type}, CPU)")
    print(f"  wake/stop : {CONFIG.wake.model} / {CONFIG.wake.stop_word}")
    print(f"  memory    : {CONFIG.memory.db_path}")
    print()
    print("Commands:  python -m esha run     (live loop)")
    print("           python spike.py        (prove the hardware)")
    return 0


def _device_arg(argv: list[str]) -> int | None:
    if "--device" in argv:
        i = argv.index("--device")
        if i + 1 < len(argv):
            return int(argv[i + 1])
    return None


def _run(argv: list[str]) -> int:
    from esha.factory import build_orchestrator

    device = _device_arg(argv)
    orch, voice_label, brain_label = build_orchestrator(
        use_ollama="--ollama" in argv, input_device=device,
    )
    dev_label = f"index {device}" if device is not None else (
        f"index {CONFIG.audio.input_device}" if CONFIG.audio.input_device is not None
        else "OS default (run `python diagnose.py` to pick your headset)"
    )
    print("=" * 60)
    print(" Esha — walking skeleton (Phase 0)")
    print(f"   brain : {brain_label}")
    print(f"   voice : {voice_label}")
    print(f"   mic   : {dev_label}")
    print(f"   VAD   : speech > {CONFIG.audio.vad_threshold:.0f} RMS, endpoint after {CONFIG.audio.vad_silence_ms}ms silence")
    print(f"   wake  : say '{CONFIG.wake.model}'  (stock word until 'Esha' is trained)")
    print("   stop  : say the stop word while she's speaking to cut her off")
    print("   Ctrl-C to quit.")
    print("=" * 60)
    from esha.audio.devices import DeviceError

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
    if argv and argv[0] == "run":
        return _run(argv[1:])
    return _status()


if __name__ == "__main__":
    raise SystemExit(main())
