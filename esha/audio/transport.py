"""LocalAudioTransport — the v1 impl of the AudioTransport contract.

Real WASAPI mic in / speaker out via sounddevice. This is the seam where the
rejected VoIP idea would slot back in as a drop-in adapter (same PCM frames in
and out); nothing else in the pipeline would change.

Half-duplex invariant lives here: `mute_input()` stops STT-bound frames flowing
while Esha speaks; `unmute_input()` re-opens AND flushes the queue so she never
transcribes the tail of her own voice (self-trigger echo).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import numpy as np
import sounddevice as sd

from esha.audio.frames import CHUNK_SAMPLES, SAMPLE_RATE


class LocalAudioTransport:
    def __init__(self, *, input_device: int | None = None, output_device: int | None = None) -> None:
        self._input_device = input_device
        self._output_device = output_device
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._muted = False

    async def capture(self) -> AsyncIterator[bytes]:
        self._loop = asyncio.get_running_loop()

        def _cb(indata, frames, time_info, status) -> None:  # noqa: ANN001 - sd callback
            # Runs on PortAudio's thread; hand the frame to the asyncio loop.
            pcm = bytes(indata)
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._offer, pcm)

        with sd.RawInputStream(
            samplerate=SAMPLE_RATE, blocksize=CHUNK_SAMPLES, dtype="int16",
            channels=1, callback=_cb, device=self._input_device,
        ):
            while True:
                yield await self._queue.get()

    def _offer(self, pcm: bytes) -> None:
        try:
            self._queue.put_nowait(pcm)
        except asyncio.QueueFull:
            pass  # drop oldest-style: better to lose a frame than to lag

    async def play(self, frames: Iterator[bytes]) -> None:
        # Chunk-wise write so the ingest task keeps running between chunks and a
        # stop-word can interrupt with ~one-chunk latency. The generator passed in
        # is the orchestrator's interruptible wrapper — it stops yielding on stop.
        stream = sd.RawOutputStream(
            samplerate=SAMPLE_RATE, dtype="int16", channels=1, device=self._output_device,
        )
        stream.start()
        try:
            for chunk in frames:
                await asyncio.to_thread(stream.write, chunk)
        finally:
            stream.stop()
            stream.close()

    def mute_input(self) -> None:
        self._muted = True

    def unmute_input(self) -> None:
        self._muted = False
        # Flush anything captured while muted (Esha's own voice tail).
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    @property
    def muted(self) -> bool:
        return self._muted


def to_int16_bytes(samples: "np.ndarray") -> bytes:
    """Helper for synthesizers: float [-1,1] or int16 array -> PCM bytes."""
    if samples.dtype != np.int16:
        samples = np.clip(samples, -1.0, 1.0)
        samples = (samples * 32767).astype(np.int16)
    return samples.tobytes()
