"""Audio auto-calibration: pick a capture gain + VAD threshold from the real mic.

Guessing a single RMS threshold across every laptop mic is hopeless (this machine's
speech peaked ~178 where the old default demanded 500). So we measure: a moment of
ambient noise, then a test phrase, and derive both a software gain (to lift quiet
mics for better STT) and a threshold that sits between the room and the voice.

The DECISION is a pure function (`recommend_audio_settings`) so it's unit-tested
with no hardware; only the measuring step touches the mic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from esha.audio.frames import CHUNK_SAMPLES, SAMPLE_RATE

TARGET_SPEECH_RMS = 2500.0   # post-gain speech level we aim for (safe: ~8% of int16 FS)
MAX_GAIN = 30.0


@dataclass(frozen=True)
class Calibration:
    noise_rms: float          # raw (pre-gain) ambient level
    speech_rms: float         # raw (pre-gain) speech level
    gain: float               # software multiplier to apply in the transport
    threshold: float          # VAD threshold in POST-gain RMS terms
    ok: bool
    message: str


def recommend_audio_settings(
    noise_rms: float, speech_rms: float, *, target_speech: float = TARGET_SPEECH_RMS
) -> Calibration:
    """Pure: given measured ambient + speech RMS (pre-gain), pick gain + threshold."""
    if speech_rms < noise_rms * 1.3 or speech_rms < 20:
        return Calibration(
            noise_rms, speech_rms, 1.0, 150.0, False,
            "Speech barely rose above the room noise. Raise your Windows mic level "
            "(Settings > Sound > Input) or move the mic closer, then recalibrate.",
        )
    gain = float(np.clip(target_speech / max(speech_rms, 1.0), 1.0, MAX_GAIN))
    noise_g = noise_rms * gain
    speech_g = speech_rms * gain
    # Sit the threshold 40% of the way from room to voice, but always clearly above room.
    threshold = noise_g + 0.40 * (speech_g - noise_g)
    threshold = max(threshold, noise_g * 1.5, 120.0)
    return Calibration(
        noise_rms, speech_rms, round(gain, 1), round(threshold), True,
        f"gain x{gain:.1f}, VAD threshold {round(threshold)} "
        f"(room~{noise_g:.0f}, voice~{speech_g:.0f} post-gain)",
    )


# ---------------------------------------------------------------------------
# Mic measurement (the only part that needs hardware)
# ---------------------------------------------------------------------------


def _measure_rms(device: int | None, seconds: float) -> list[float]:
    import sounddevice as sd

    rms: list[float] = []
    n_frames = max(1, int(seconds * SAMPLE_RATE / CHUNK_SAMPLES))
    with sd.InputStream(samplerate=SAMPLE_RATE, blocksize=CHUNK_SAMPLES,
                        channels=1, dtype="int16", device=device) as stream:
        for _ in range(n_frames):
            data, _over = stream.read(CHUNK_SAMPLES)
            s = np.asarray(data, dtype=np.int16).reshape(-1).astype(np.float64)
            rms.append(float(np.sqrt(np.mean(s ** 2))) if s.size else 0.0)
    return rms


def calibrate(device: int | None, *, ambient_s: float = 2.0, speech_s: float = 3.0) -> Calibration:
    """Interactive: measure ambient, then a test phrase; return a recommendation."""
    print(f"\n  Calibrating mic (device {device if device is not None else 'default'})...")
    print(f"  1) Stay SILENT for {ambient_s:.0f}s (measuring the room)...", flush=True)
    time.sleep(0.4)
    noise = _measure_rms(device, ambient_s)

    print(f"  2) Now SAY A SENTENCE for {speech_s:.0f}s "
          "(e.g. 'hey esha, what's the weather like today')...", flush=True)
    speech = _measure_rms(device, speech_s)

    noise_rms = float(np.percentile(noise, 90)) if noise else 0.0   # above nearly all room noise
    speech_rms = float(np.percentile(speech, 75)) if speech else 0.0  # sustained speech, not just peak
    result = recommend_audio_settings(noise_rms, speech_rms)
    print(f"  -> measured room~{noise_rms:.0f}, voice~{speech_rms:.0f} (raw)")
    print(f"  -> {result.message}")
    return result
