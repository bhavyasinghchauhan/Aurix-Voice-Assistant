"""
Voice pipeline smoke test (no LLM, no Claude API).

Exercises the three voice components in isolation:
  1. Wake word detection (openWakeWord)
  2. Speech-to-text       (Google free STT via SpeechRecognition)
  3. Text-to-speech       (pyttsx3, offline)

Default flow:
    TTS greeting -> wait for wake word -> STT -> echo via TTS -> repeat

Run from the project root:
    python test_voice_only.py
    python test_voice_only.py --rounds 3
    python test_voice_only.py --skip-wake-word
    python test_voice_only.py --wake-word alexa --threshold 0.6
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

# Force UTF-8 stdout (Windows cp1252 console hates non-ASCII)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def info(msg: str) -> None:
    print(f"  [..]   {msg}")


async def run_one_round(stt, tts, wake_word, skip_wake_word: bool, round_num: int) -> bool:
    """One full wake -> listen -> echo cycle. Returns False to stop the loop."""
    print()
    print(f"=== Round {round_num} ===")

    if not skip_wake_word:
        info(f"Listening for wake word... (say it now)")
        try:
            detected = await wake_word.detect()
        except KeyboardInterrupt:
            return False
        except Exception as e:
            fail(f"Wake word detection error: {e}")
            return False
        if not detected:
            return True
        ok("Wake word detected")
    else:
        info("Skipping wake word — straight to STT")

    # Beep verbally so the user knows the mic is hot
    await tts.speak("Yes?")

    info("Listening for command via Google STT...")
    try:
        command = await stt.listen(timeout=5)
    except KeyboardInterrupt:
        return False
    except Exception as e:
        fail(f"STT error: {e}")
        return True

    if not command:
        ok("STT returned nothing (silence or unrecognized)")
        await tts.speak("I didn't catch that")
        return True

    ok(f"Heard: {command!r}")
    await tts.speak(f"You said: {command}")
    return True


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test the AURIX voice pipeline without calling Claude."
    )
    parser.add_argument(
        "--wake-word", default="jarvis",
        help="Wake word: jarvis, alexa, mycroft, rhasspy. Default: jarvis",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.5,
        help="Wake word trigger threshold (0.0 - 1.0). Default: 0.5",
    )
    parser.add_argument(
        "--rounds", type=int, default=0,
        help="Number of wake/listen/echo rounds before exiting. 0 = forever",
    )
    parser.add_argument(
        "--skip-wake-word", action="store_true",
        help="Skip wake-word stage; jump straight to STT each round",
    )
    parser.add_argument(
        "--language", default="en-US",
        help="STT language code. Default: en-US",
    )
    parser.add_argument(
        "--tts-rate", type=int, default=175,
        help="TTS speech rate (words/min). Default: 175",
    )
    parser.add_argument(
        "--list-mics", action="store_true",
        help="Print all available microphones with their indices and exit",
    )
    parser.add_argument(
        "--mic-index", type=int, default=None,
        help="Use the microphone at this PyAudio device index (see --list-mics)",
    )
    parser.add_argument(
        "--mic-name", default=None,
        help="Use the first microphone whose name contains this substring",
    )
    args = parser.parse_args()

    # --list-mics is a one-shot info dump and exits before touching anything else
    if args.list_mics:
        try:
            from voice.speech_to_text import list_microphones, find_preferred_microphone
        except ImportError as e:
            print(f"Cannot import voice.speech_to_text: {e}")
            return 1
        mics = list_microphones()
        if not mics:
            print("No microphones detected.")
            return 1
        print("Available microphones:")
        print("  idx  name")
        print("  ---  ----")
        for idx, name in mics:
            print(f"  {idx:>3}  {name}")
        preferred = find_preferred_microphone()
        print()
        if preferred is not None:
            pidx, pname = preferred
            print(f"Preferred (auto-selected): [{pidx}] {pname}")
        else:
            print("No preferred mic detected — would use system default.")
        print()
        print("Use --mic-index N or --mic-name SUBSTRING to override.")
        return 0

    print("AURIX voice pipeline test")
    print("=========================")
    print("This script does NOT call the Claude API.")
    print("Press Ctrl+C at any time to quit.")

    # ─── 1. TTS init ────────────────────────────────────────────────────────
    section("1. Text-to-speech (pyttsx3, offline)")
    try:
        from voice.text_to_speech import TextToSpeech
    except ImportError as e:
        fail(f"cannot import TextToSpeech: {e}")
        return 1

    try:
        tts = TextToSpeech(rate=args.tts_rate, volume=0.9)
        ok(f"TTS engine ready (rate={args.tts_rate})")
    except Exception as e:
        fail(f"TTS init failed: {e}")
        return 1

    info("Speaking greeting...")
    try:
        await tts.speak("Voice pipeline test starting. Can you hear me?")
        ok("TTS playback complete")
    except Exception as e:
        fail(f"TTS playback error: {e}")
        return 1

    # ─── 2. STT init ────────────────────────────────────────────────────────
    section("2. Speech-to-text (Google free STT)")
    try:
        from voice.speech_to_text import SpeechToText
    except ImportError as e:
        fail(f"cannot import SpeechToText: {e}")
        return 1

    try:
        stt = SpeechToText(
            language=args.language,
            device_index=args.mic_index,
            device_name=args.mic_name,
        )
        if stt.device_index is not None:
            ok(f"STT ready (language={args.language}, mic_index={stt.device_index})")
        else:
            ok(f"STT ready (language={args.language}, mic=system default)")
    except Exception as e:
        fail(f"STT init failed: {e}")
        return 1

    # ─── 3. Wake word init ──────────────────────────────────────────────────
    wake_word = None
    if not args.skip_wake_word:
        section("3. Wake word detector (openWakeWord)")
        try:
            from voice.wake_word_detector import WakeWordDetector
        except ImportError as e:
            fail(f"cannot import WakeWordDetector: {e}")
            return 1

        try:
            wake_word = WakeWordDetector(
                wake_word=args.wake_word,
                threshold=args.threshold,
            )
            info(f"Loading openWakeWord model for '{args.wake_word}'...")
            wake_word._lazy_init()
            ok(f"Wake word ready (model={wake_word.model_id} threshold={args.threshold})")
        except Exception as e:
            fail(f"Wake word init failed: {e}")
            return 1
    else:
        section("3. Wake word detector — SKIPPED")

    # ─── 4. Loop ─────────────────────────────────────────────────────────────
    section("4. Interactive test loop")
    if args.rounds > 0:
        print(f"  Running {args.rounds} round(s).")
    else:
        print("  Running until Ctrl+C.")

    round_num = 0
    try:
        while True:
            round_num += 1
            if args.rounds > 0 and round_num > args.rounds:
                break
            cont = await run_one_round(
                stt=stt,
                tts=tts,
                wake_word=wake_word,
                skip_wake_word=args.skip_wake_word,
                round_num=round_num,
            )
            if not cont:
                break
    except KeyboardInterrupt:
        print()
        info("Interrupted by user")
    finally:
        if wake_word is not None:
            try:
                wake_word.cleanup()
            except Exception:
                pass

    section("Done")
    print(f"  Completed {round_num - 1 if round_num > args.rounds and args.rounds > 0 else round_num} round(s).")
    print("  All voice components reachable.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nQuit.")
        sys.exit(0)
