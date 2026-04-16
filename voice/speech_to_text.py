"""Speech-to-text engine."""
import asyncio
from typing import List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)


# Substrings used to auto-pick a preferred mic when no explicit selection is
# made. First match wins. Lower-case; checked with `in`.
PREFERRED_MIC_PATTERNS = (
    "asus ai noise",      # ASUS AI Noise-cancelling Mic
    "asus ai noise-cancelling",
    "asus noise",
)


def list_microphones() -> List[Tuple[int, str]]:
    """Return [(index, name), ...] for every input device PyAudio sees."""
    import speech_recognition as sr

    return list(enumerate(sr.Microphone.list_microphone_names()))


def find_microphone(query: str) -> Optional[int]:
    """
    Resolve a mic by case-insensitive substring match against its name.
    Returns the device index, or None if no mic matches.
    """
    if not query:
        return None
    needle = query.lower()
    for idx, name in list_microphones():
        if needle in name.lower():
            return idx
    return None


def find_preferred_microphone() -> Optional[Tuple[int, str]]:
    """
    Look for a 'preferred' mic (currently: ASUS AI Noise-cancelling).
    Returns (index, name) or None.
    """
    mics = list_microphones()
    for pattern in PREFERRED_MIC_PATTERNS:
        for idx, name in mics:
            if pattern in name.lower():
                return idx, name
    return None


class SpeechToText:
    """
    Wraps speech_recognition for command transcription.
    Listens for one utterance and returns the text.

    Microphone selection priority on construction:
      1. Explicit `device_index` argument
      2. `device_name` substring match (case-insensitive)
      3. Auto-detect ASUS AI Noise-cancelling mic
      4. System default microphone
    """

    def __init__(
        self,
        language: str = "en-US",
        device_index: Optional[int] = None,
        device_name: Optional[str] = None,
        list_on_init: bool = True,
    ):
        self.language = language
        import speech_recognition as sr

        self._sr = sr
        self.recognizer = sr.Recognizer()

        # Always discover what's available so logs / debugging is easy.
        mics = list_microphones()
        if list_on_init:
            self._log_available_mics(mics)

        self.device_index = self._resolve_device(device_index, device_name, mics)

        if self.device_index is not None:
            name = next((n for i, n in mics if i == self.device_index), "?")
            logger.info(f"STT using mic [{self.device_index}]: {name}")
        else:
            logger.info("STT using system default microphone")

    # ─── Mic resolution ─────────────────────────────────────────────────────

    def _resolve_device(
        self,
        device_index: Optional[int],
        device_name: Optional[str],
        mics: List[Tuple[int, str]],
    ) -> Optional[int]:
        # 1. Explicit index wins
        if device_index is not None:
            valid = [i for i, _ in mics]
            if device_index in valid:
                return device_index
            logger.warning(
                f"Requested mic index {device_index} not in {valid}; "
                f"falling back to default"
            )

        # 2. Explicit name substring
        if device_name:
            idx = find_microphone(device_name)
            if idx is not None:
                return idx
            logger.warning(
                f"No mic matching {device_name!r}; falling back to preferred/default"
            )

        # 3. Preferred (ASUS AI Noise-cancelling)
        preferred = find_preferred_microphone()
        if preferred is not None:
            idx, name = preferred
            logger.info(f"Auto-selected preferred mic [{idx}]: {name}")
            return idx

        # 4. System default
        return None

    @staticmethod
    def _log_available_mics(mics: List[Tuple[int, str]]) -> None:
        if not mics:
            logger.warning("No microphones detected")
            return
        logger.info(f"Detected {len(mics)} microphone input(s):")
        for idx, name in mics:
            logger.info(f"  [{idx:>2}] {name}")

    # ─── Capture ────────────────────────────────────────────────────────────

    async def listen(self, timeout: int = 5, phrase_time_limit: int = 10) -> Optional[str]:
        """Listen for a single user command. Returns transcribed text or None."""
        loop = asyncio.get_event_loop()

        def _capture():
            mic = (
                self._sr.Microphone(device_index=self.device_index)
                if self.device_index is not None
                else self._sr.Microphone()
            )
            with mic as source:
                logger.debug("Listening for command...")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                try:
                    return self.recognizer.listen(
                        source, timeout=timeout, phrase_time_limit=phrase_time_limit
                    )
                except self._sr.WaitTimeoutError:
                    return None

        audio = await loop.run_in_executor(None, _capture)
        if audio is None:
            logger.debug("No speech detected")
            return None

        try:
            text = await loop.run_in_executor(
                None, lambda: self.recognizer.recognize_google(audio, language=self.language)
            )
            logger.info(f"Heard: {text}")
            return text
        except self._sr.UnknownValueError:
            logger.debug("Could not understand audio")
            return None
        except self._sr.RequestError as e:
            logger.error(f"Speech recognition error: {e}")
            return None
