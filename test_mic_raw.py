"""
Raw microphone capture test — bypasses openWakeWord, SpeechRecognition, and
pyttsx3 entirely. Talks directly to PyAudio so we can prove (or disprove)
that the OS is actually delivering audio frames from the device.

What it does:
  1. Opens PyAudio device index 15 (ASUS AI Noise-cancelling Mic by default)
  2. Captures 5 seconds of mono 16-bit PCM at 16 kHz
  3. Shows a live RMS amplitude bar while recording
  4. Saves the result to test_recording.wav
  5. Prints a verdict: silent / very quiet / normal / loud / clipping

Run from the project root:
    python test_mic_raw.py
    python test_mic_raw.py --index 3 --seconds 10
    python test_mic_raw.py --list

This is the lowest-level test we have. If THIS doesn't capture sound, the
problem is with the device, the driver, or Windows mic permissions —
nothing in AURIX can fix it.
"""
import argparse
import math
import struct
import sys
import time
import wave
from pathlib import Path

# Force UTF-8 stdout (Windows cp1252 console hates non-ASCII)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2  # int16 = 2 bytes
CHUNK_SIZE = 1024  # ~64 ms at 16 kHz — fast enough for responsive bar updates
INT16_MAX = 32767


def rms_int16(samples: bytes) -> float:
    """Root-mean-square amplitude of an int16 PCM byte buffer."""
    n = len(samples) // 2
    if n == 0:
        return 0.0
    fmt = f"{n}h"
    ints = struct.unpack(fmt, samples)
    total = sum(s * s for s in ints)
    return math.sqrt(total / n)


def peak_int16(samples: bytes) -> int:
    """Peak absolute amplitude of an int16 PCM byte buffer."""
    n = len(samples) // 2
    if n == 0:
        return 0
    fmt = f"{n}h"
    ints = struct.unpack(fmt, samples)
    return max(abs(s) for s in ints)


def list_devices(pa) -> None:
    print("Input devices:")
    print("  idx  ch  rate    name")
    print("  ---  --  ----    ----")
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info.get("maxInputChannels", 0) > 0:
            print(
                f"  {i:>3}  {int(info['maxInputChannels']):>2}  "
                f"{int(info['defaultSampleRate']):>5}   {info['name']}"
            )


def classify_level(rms: float) -> str:
    """Map an RMS amplitude (0..32767) to a friendly verdict."""
    if rms < 30:
        return "SILENT (mic is dead, muted, or wrong device)"
    if rms < 150:
        return "VERY QUIET (background hiss only — was anyone speaking?)"
    if rms < 1000:
        return "QUIET (audible but low — try moving closer or raising input gain)"
    if rms < 6000:
        return "NORMAL (good speech level)"
    if rms < 15000:
        return "LOUD (might be too hot for STT — slightly lower gain)"
    return "CLIPPING (signal hitting the rails — lower input gain immediately)"


def main() -> int:
    parser = argparse.ArgumentParser(description="Raw PyAudio microphone capture test")
    parser.add_argument(
        "--index", type=int, default=15,
        help="PyAudio device index to record from. Default: 15 (ASUS AI Noise-cancelling)",
    )
    parser.add_argument(
        "--seconds", type=int, default=5,
        help="Recording duration in seconds. Default: 5",
    )
    parser.add_argument(
        "--output", default="test_recording.wav",
        help="WAV output path. Default: test_recording.wav",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List input devices and exit",
    )
    args = parser.parse_args()

    try:
        import pyaudio
    except ImportError:
        print("FAIL: pyaudio not installed.")
        print("      pip install pyaudio")
        print("      (Windows: if pip fails, grab a wheel from")
        print("       https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio)")
        return 1

    pa = pyaudio.PyAudio()

    try:
        if args.list:
            list_devices(pa)
            return 0

        # Validate the requested device exists and is an input
        try:
            info = pa.get_device_info_by_index(args.index)
        except Exception as e:
            print(f"FAIL: cannot query device index {args.index}: {e}")
            print()
            list_devices(pa)
            return 1

        max_in = int(info.get("maxInputChannels", 0))
        if max_in <= 0:
            print(f"FAIL: device {args.index} ({info.get('name')!r}) has no input channels")
            print()
            list_devices(pa)
            return 1

        print("Raw microphone capture test")
        print("===========================")
        print(f"  Device     : [{args.index}] {info.get('name')}")
        print(f"  Format     : {SAMPLE_RATE} Hz, mono, int16")
        print(f"  Duration   : {args.seconds}s")
        print(f"  Output     : {args.output}")
        print()
        print("Speak normally into the mic. Watch the live amplitude bar.")
        print()

        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                input_device_index=args.index,
                frames_per_buffer=CHUNK_SIZE,
            )
        except Exception as e:
            print(f"FAIL: could not open stream on device {args.index}: {e}")
            print()
            print("Likely causes:")
            print("  - Device in use by another app")
            print("  - Windows microphone permission denied")
            print("    (Settings -> Privacy -> Microphone -> allow desktop apps)")
            print("  - Device doesn't support 16 kHz mono int16")
            return 1

        frames: list[bytes] = []
        bar_width = 40
        chunks_needed = int(SAMPLE_RATE / CHUNK_SIZE * args.seconds)

        all_time_peak = 0
        all_time_rms_sum = 0.0
        all_time_rms_count = 0
        nonzero_chunks = 0

        countdown_lines = ["3...", "2...", "1...", "RECORDING"]
        for line in countdown_lines:
            print(f"  {line}")
            time.sleep(0.4 if line != "RECORDING" else 0)

        print()
        start = time.monotonic()
        for chunk_idx in range(chunks_needed):
            try:
                data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            except Exception as e:
                print(f"\nFAIL: read error after {chunk_idx} chunks: {e}")
                stream.stop_stream()
                stream.close()
                return 1
            frames.append(data)

            rms = rms_int16(data)
            peak = peak_int16(data)
            if peak > 0:
                nonzero_chunks += 1
            all_time_peak = max(all_time_peak, peak)
            all_time_rms_sum += rms
            all_time_rms_count += 1

            # Log scale makes the bar useful across the full int16 range
            db_norm = 0.0
            if rms > 0:
                db_norm = max(0.0, min(1.0, (math.log10(rms + 1) / math.log10(INT16_MAX))))
            filled = int(db_norm * bar_width)
            bar = "#" * filled + "-" * (bar_width - filled)

            elapsed = time.monotonic() - start
            remaining = max(0.0, args.seconds - elapsed)
            print(
                f"\r  [{bar}]  rms={rms:>6.0f}  peak={peak:>5}  t-{remaining:4.1f}s ",
                end="",
                flush=True,
            )

        stream.stop_stream()
        stream.close()
        print()
        print()

        # ─── Save WAV ───────────────────────────────────────────────────────
        out_path = Path(args.output)
        try:
            with wave.open(str(out_path), "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(SAMPLE_WIDTH)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(b"".join(frames))
            print(f"  Saved {out_path.resolve()}")
            print(f"         {out_path.stat().st_size:,} bytes")
        except Exception as e:
            print(f"  WARN: could not save WAV: {e}")

        # ─── Verdict ────────────────────────────────────────────────────────
        avg_rms = all_time_rms_sum / max(1, all_time_rms_count)
        nonzero_pct = 100.0 * nonzero_chunks / max(1, all_time_rms_count)

        print()
        print("Capture summary")
        print("---------------")
        print(f"  Chunks captured  : {len(frames)}")
        print(f"  Non-zero chunks  : {nonzero_chunks} ({nonzero_pct:.1f}%)")
        print(f"  Average RMS      : {avg_rms:.0f}")
        print(f"  Peak amplitude   : {all_time_peak} / {INT16_MAX}")
        print()
        verdict = classify_level(avg_rms)
        print(f"  Verdict: {verdict}")
        print()

        if avg_rms < 30:
            print("  Diagnosis:")
            print("    The mic is connected and the stream opened, but no audio")
            print("    is coming through. Check (in this order):")
            print("      1. Windows Settings -> Privacy -> Microphone -> ON")
            print("         and 'Let desktop apps access your microphone' -> ON")
            print("      2. Sound Settings -> Input -> pick this device, raise level")
            print("      3. Physical mute switch on the headset/mic")
            print("      4. Try a different device index: python test_mic_raw.py --list")
            return 2

        if all_time_peak >= INT16_MAX - 1:
            print("  Note: peak hit the int16 ceiling — signal is clipping.")
            print("        Lower the input level in Windows Sound Settings.")

        print(f"  -> Mic is working. Play back {args.output} to confirm.")
        return 0

    finally:
        pa.terminate()


if __name__ == "__main__":
    sys.exit(main())
