"""Text-to-speech engine (gTTS + pygame.mixer)."""
import asyncio
import hashlib
import math
import os
import random
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


# Disk cache for synthesized phrases. Repeated lines like "Yes?" or
# "I didn't catch that" pay the network cost once and then play instantly.
DEFAULT_CACHE_DIR = Path(
    os.environ.get(
        "AURIX_TTS_CACHE", Path.home() / ".aurix" / "tts_cache"
    )
)


class TextToSpeech:
    """
    TTS using Google Text-to-Speech (gTTS) for synthesis and pygame.mixer
    for playback. Replaces pyttsx3, which hangs intermittently on Windows.

    Trade-offs vs pyttsx3:
      + Reliable on Windows, no blocking-init quirks
      + Higher quality voice
      + Cross-platform (Windows/macOS/Linux)
      - Requires internet (gTTS hits the Google Translate TTS endpoint)
      - No real `rate` control without ffmpeg post-processing
        (we expose `slow=` for slower speech only)

    Cached: identical (text, lang, slow) calls reuse the same MP3 file.
    """

    def __init__(
        self,
        rate: int = 175,
        volume: float = 0.9,
        lang: str = "en",
        tld: str = "com",
        cache_dir: Optional[Path] = None,
    ):
        self.rate = rate
        self.volume = max(0.0, min(1.0, volume))
        self.lang = lang
        self.tld = tld
        self.slow = rate < 130

        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._mixer_ready = False
        self._audio_callback = None

    def set_audio_callback(self, callback) -> None:
        """Register a callback(low, mid, high, amp) called during playback."""
        self._audio_callback = callback

    # ─── Setup ───────────────────────────────────────────────────────────────

    def _ensure_mixer(self) -> None:
        if self._mixer_ready:
            return
        try:
            import pygame
        except ImportError as e:
            logger.error("pygame not installed — required for TTS playback")
            raise

        # Initialize the audio subsystem only. Avoids spinning up the full
        # pygame display when we just want sound.
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=24000, size=-16, channels=1, buffer=512)
        pygame.mixer.music.set_volume(self.volume)
        self._mixer_ready = True

    # ─── Cache ───────────────────────────────────────────────────────────────

    def _cache_path(self, text: str) -> Path:
        key = f"{self.lang}|{self.tld}|{int(self.slow)}|{text}"
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{digest}.mp3"

    def _synthesize(self, text: str, path: Path) -> None:
        """Call gTTS to render `text` to `path`. Blocking — caller wraps it."""
        from gtts import gTTS

        tts = gTTS(text=text, lang=self.lang, tld=self.tld, slow=self.slow)
        # Write atomically — partial files would poison the cache forever
        tmp = path.with_suffix(".tmp.mp3")
        tts.save(str(tmp))
        os.replace(tmp, path)

    # ─── Playback ────────────────────────────────────────────────────────────

    def _play_blocking(self, path: Path) -> None:
        import pygame

        self._ensure_mixer()
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.set_volume(self.volume)
        pygame.mixer.music.play()

        t = 0.0
        while pygame.mixer.music.get_busy():
            if self._audio_callback:
                low = 0.4 + 0.3 * math.sin(t * 2.1) + random.uniform(-0.05, 0.05)
                mid = 0.3 + 0.2 * math.sin(t * 3.4) + random.uniform(-0.05, 0.05)
                high = 0.2 + 0.15 * math.sin(t * 5.7) + random.uniform(-0.03, 0.03)
                amp = 0.35 + 0.25 * math.sin(t * 1.8) + random.uniform(-0.05, 0.05)
                try:
                    self._audio_callback(
                        max(0.0, min(1.0, low)),
                        max(0.0, min(1.0, mid)),
                        max(0.0, min(1.0, high)),
                        max(0.0, min(1.0, amp)),
                    )
                except Exception:
                    pass
                t += 0.05

            time.sleep(0.05)

        if self._audio_callback:
            try:
                self._audio_callback(0.0, 0.0, 0.0, 0.0)
            except Exception:
                pass

        try:
            pygame.mixer.music.unload()
        except AttributeError:
            pass

    # ─── Public async API ────────────────────────────────────────────────────

    async def speak(self, text: str) -> None:
        if not text or not text.strip():
            return

        logger.info(f"Speaking: {text}")
        cache_path = self._cache_path(text)
        loop = asyncio.get_event_loop()

        # 1. Synthesize if not cached
        if not cache_path.exists():
            try:
                await loop.run_in_executor(None, self._synthesize, text, cache_path)
            except Exception as e:
                logger.error(f"gTTS synthesis failed: {e}")
                return

        # 2. Play
        try:
            await loop.run_in_executor(None, self._play_blocking, cache_path)
        except Exception as e:
            logger.error(f"Audio playback failed: {e}")

    def set_rate(self, rate: int) -> None:
        """Back-compat shim. gTTS only has slow on/off."""
        self.rate = rate
        self.slow = rate < 130

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))
        if self._mixer_ready:
            import pygame

            pygame.mixer.music.set_volume(self.volume)

    def clear_cache(self) -> int:
        """Delete all cached TTS audio. Returns count removed."""
        count = 0
        for f in self.cache_dir.glob("*.mp3"):
            try:
                f.unlink()
                count += 1
            except OSError:
                pass
        return count
