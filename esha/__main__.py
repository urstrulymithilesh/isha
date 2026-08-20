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
    from esha.audio.calibrate import calibrate
    from esha.audio.devices import DeviceError, validate_input_device

    device = _effective_device(_device_arg(argv))
    try:
        validate_input_device(device)
        result = calibrate(device)
    except DeviceError as e:
        print(f"\n{e}")
        return 1
    print("\n  Put these in esha/config.py -> AudioConfig to make them permanent:")
    print(f"      capture_gain: float = {result.gain}")
    print(f"      vad_threshold: float = {result.threshold}")
    if not result.ok:
        print("  (calibration was not confident — see the message above)")
    return 0


def _run(argv: list[str]) -> int:
    from esha.audio.calibrate import calibrate
    from esha.audio.devices import DeviceError

    from esha.factory import build_orchestrator

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
    print(" Esha — walking skeleton (Phase 0)")
    print(f"   brain : {brain_label}")
    print(f"   voice : {voice_label}")
    print(f"   mic   : {dev_label}  (gain x{orch.transport.gain:.1f})")
    print(f"   VAD   : speech > {orch.vad.threshold:.0f} RMS, endpoint after {CONFIG.audio.vad_silence_ms}ms silence")
    print(f"   wake  : say '{CONFIG.wake.model}'  (stock word until 'Esha' is trained)")
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
    if argv and argv[0] == "run":
        return _run(argv[1:])
    return _status()


if __name__ == "__main__":
    raise SystemExit(main())
