"""Always-listening wake word detector (openWakeWord backend)."""
import asyncio
from pathlib import Path
from typing import Optional

import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)


# openWakeWord ships several pre-trained models. Map AURIX wake-word names
# to the model id you'd pass to `Model(wakeword_models=[...])`.
BUILTIN_MODELS = {
    "jarvis": "hey_jarvis",
    "hey_jarvis": "hey_jarvis",
    "aurix": "hey_jarvis",
    "hey_aurix": "hey_jarvis",
    "alexa": "alexa",
    "mycroft": "hey_mycroft",
    "hey_mycroft": "hey_mycroft",
    "rhasspy": "hey_rhasspy",
    "hey_rhasspy": "hey_rhasspy",
}


class WakeWordDetector:
    """
    Continuously listens for a wake word using openWakeWord.

    openWakeWord is actively maintained, fully offline, free, and works on
    Python 3.10+ including 3.12 — unlike Snowboy/Porcupine. Models are
    downloaded automatically on first run (~10 MB).

    Reads 80 ms PCM frames at 16 kHz mono and yields between frames so the
    asyncio event loop stays responsive.

    Custom models: pass an absolute path to a `.onnx` or `.tflite` model
    file via `model_path` to use your own trained wake word.
    """

    SAMPLE_RATE = 16_000
    CHUNK_SIZE = 1280  # openWakeWord's native frame size (80 ms @ 16 kHz)

    def __init__(
        self,
        wake_word: str = "jarvis",
        model_path: Optional[str] = None,
        threshold: float = 0.5,
        inference_framework: str = "onnx",
    ):
        self.wake_word = wake_word
        self.threshold = threshold
        self.inference_framework = inference_framework

        # Resolve model: explicit path > built-in mapping > fallback
        if model_path:
            if not Path(model_path).exists():
                raise FileNotFoundError(f"Wake word model not found: {model_path}")
            self.model_id = model_path
        else:
            self.model_id = BUILTIN_MODELS.get(wake_word.lower(), "hey_jarvis")
            if wake_word.lower() not in BUILTIN_MODELS:
                logger.warning(
                    f"No built-in model for '{wake_word}', falling back to 'hey_jarvis'. "
                    f"Built-in options: {sorted(BUILTIN_MODELS)}"
                )

        self.model = None
        self.pa = None
        self.audio_stream = None
        self._initialized = False

    def _lazy_init(self) -> None:
        if self._initialized:
            return
        try:
            from openwakeword.model import Model
            from openwakeword.utils import download_models
        except ImportError as e:
            logger.error(
                "openwakeword not installed. Run: pip install openwakeword"
            )
            raise

        # Pull built-in models on first run. No-op if already cached.
        try:
            download_models()
        except Exception as e:
            logger.debug(f"download_models() skipped: {e}")

        try:
            self.model = Model(
                wakeword_models=[self.model_id],
                inference_framework=self.inference_framework,
            )
        except Exception as e:
            logger.error(f"Failed to load wake word model '{self.model_id}': {e}")
            raise

        try:
            import pyaudio
        except ImportError:
            logger.error("pyaudio not installed")
            raise

        self.pa = pyaudio.PyAudio()
        self._initialized = True
        logger.info(
            f"openWakeWord initialized: model={self.model_id} threshold={self.threshold}"
        )

    async def detect(self) -> bool:
        """Listen until the wake word is detected. Returns True on hit."""
        self._lazy_init()
        import pyaudio

        self.audio_stream = self.pa.open(
            rate=self.SAMPLE_RATE,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self.CHUNK_SIZE,
        )

        try:
            while True:
                pcm = self.audio_stream.read(
                    self.CHUNK_SIZE, exception_on_overflow=False
                )
                audio = np.frombuffer(pcm, dtype=np.int16)

                # predict() returns {model_name: score in [0, 1]}
                scores = self.model.predict(audio)

                for name, score in scores.items():
                    if score >= self.threshold:
                        logger.info(
                            f"Wake word detected: model={name} score={score:.3f}"
                        )
                        return True

                # Yield to the event loop between frames
                await asyncio.sleep(0)
        finally:
            if self.audio_stream is not None:
                try:
                    self.audio_stream.stop_stream()
                    self.audio_stream.close()
                except Exception:
                    pass
                self.audio_stream = None

    def cleanup(self) -> None:
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None
        if self.pa is not None:
            self.pa.terminate()
            self.pa = None
        self.model = None
        self._initialized = False


# ─── Calibration smoke test ──────────────────────────────────────────────────
#
# Run from the project root:
#
#     python -m voice.wake_word_detector
#     python -m voice.wake_word_detector --wake-word jarvis --threshold 0.5
#     python -m voice.wake_word_detector --wake-word alexa --duration 30
#
# Speak your wake phrase a few times. Watch the live score bar, then set
# `wakeword_threshold` in config/settings.yaml to a value just above the
# highest score you see when NOT saying the wake word, and well below the
# scores you get when you DO say it.

def _run_calibration() -> int:
    import argparse
    import sys
    import time

    parser = argparse.ArgumentParser(
        description="Live wake-word calibration. Speak into the mic; press Ctrl+C to quit."
    )
    parser.add_argument(
        "--wake-word",
        default="jarvis",
        help="Wake word to listen for (jarvis, alexa, mycroft, rhasspy). Default: jarvis",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Trigger threshold (0.0 - 1.0). Default: 0.5",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help="Stop after N seconds (0 = run until Ctrl+C). Default: 0",
    )
    parser.add_argument(
        "--model-path",
        default=None,
        help="Optional path to a custom .onnx/.tflite wake-word model",
    )
    args = parser.parse_args()

    # Force UTF-8 stdout so the bar renders cleanly on Windows.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print(f"Loading openWakeWord model for '{args.wake_word}'...")
    detector = WakeWordDetector(
        wake_word=args.wake_word,
        model_path=args.model_path,
        threshold=args.threshold,
    )

    try:
        detector._lazy_init()
    except Exception as e:
        print(f"FAILED to initialize: {e}")
        return 1

    import pyaudio  # safe — _lazy_init imported it already

    stream = detector.pa.open(
        rate=detector.SAMPLE_RATE,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=detector.CHUNK_SIZE,
    )

    bar_width = 30
    threshold_pos = int(args.threshold * bar_width)
    peak_score = 0.0
    rolling_peak = 0.0
    rolling_window_frames = int(2.0 / 0.08)  # ~2 seconds of 80ms frames
    rolling_buffer: list[float] = []
    detection_count = 0
    last_detection_time = 0.0
    detection_cooldown = 1.0  # seconds — avoid double-firing on one utterance

    print()
    print(f"Listening on default microphone @ {detector.SAMPLE_RATE} Hz")
    print(f"Model:     {detector.model_id}")
    print(f"Threshold: {args.threshold}")
    print()
    print("Say your wake phrase a few times. Watch the live score bar.")
    print("Tip: set wakeword_threshold just above what you see when SILENT,")
    print("     and well below the scores you hit when SAYING the wake word.")
    print("Press Ctrl+C to stop.")
    print()
    print("  score | peak(2s) | bar")
    print("  ------+----------+" + "-" * (bar_width + 2))

    start_time = time.monotonic()
    try:
        while True:
            if args.duration > 0 and (time.monotonic() - start_time) >= args.duration:
                break

            pcm = stream.read(detector.CHUNK_SIZE, exception_on_overflow=False)
            audio = np.frombuffer(pcm, dtype=np.int16)
            scores = detector.model.predict(audio)

            # Take the max across all loaded model heads (we only loaded one,
            # but predict() always returns a dict).
            score = max(scores.values()) if scores else 0.0

            rolling_buffer.append(score)
            if len(rolling_buffer) > rolling_window_frames:
                rolling_buffer.pop(0)
            rolling_peak = max(rolling_buffer)

            if score > peak_score:
                peak_score = score

            # Build a fixed-width bar with a threshold marker `|`.
            filled = min(bar_width, int(score * bar_width))
            bar_chars = []
            for i in range(bar_width):
                if i == threshold_pos:
                    bar_chars.append("|")
                elif i < filled:
                    bar_chars.append("#")
                else:
                    bar_chars.append("-")
            bar = "".join(bar_chars)

            now = time.monotonic()
            triggered = (
                score >= args.threshold
                and (now - last_detection_time) > detection_cooldown
            )
            if triggered:
                detection_count += 1
                last_detection_time = now
                # Use \n so the trigger line stays in scrollback
                print(
                    f"\r  {score:.3f} |  {rolling_peak:.3f}  | [{bar}]  "
                    f"*** DETECTED #{detection_count} ***"
                )
            else:
                # \r overwrite for the rolling display
                print(
                    f"\r  {score:.3f} |  {rolling_peak:.3f}  | [{bar}]      ",
                    end="",
                    flush=True,
                )

    except KeyboardInterrupt:
        print()
        print()
        print("Stopped.")
    finally:
        try:
            stream.stop_stream()
            stream.close()
        except Exception:
            pass
        detector.cleanup()

    print()
    print("Calibration summary")
    print("-------------------")
    print(f"  All-time peak score : {peak_score:.3f}")
    print(f"  Detections fired    : {detection_count} (threshold={args.threshold})")
    print()
    if peak_score < args.threshold:
        print(f"  Suggestion: peak ({peak_score:.3f}) never crossed threshold "
              f"({args.threshold}).")
        print(f"              Try lowering wakeword_threshold to "
              f"{max(0.05, peak_score - 0.05):.2f} in settings.yaml.")
    elif peak_score > args.threshold + 0.3:
        suggested = min(0.95, args.threshold + 0.15)
        print(f"  Suggestion: lots of headroom ({peak_score:.3f} vs "
              f"{args.threshold}).")
        print(f"              You can raise wakeword_threshold to ~{suggested:.2f} "
              f"to reduce false positives.")
    else:
        print(f"  Threshold {args.threshold} looks reasonable for this mic/room.")

    return 0


if __name__ == "__main__":
    raise SystemExit(_run_calibration())
