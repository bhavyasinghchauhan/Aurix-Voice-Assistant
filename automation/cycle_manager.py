"""Save / load named macro cycles to disk."""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

CYCLES_DIR = Path(
    os.environ.get("AURIX_CYCLES_DIR", Path.home() / ".aurix" / "cycles")
)


class CycleManager:
    """Persists named action cycles (macros) to JSON files."""

    def __init__(self, directory: Optional[Path] = None):
        self.directory = Path(directory) if directory else CYCLES_DIR
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, name: str, actions: List[Dict]) -> Path:
        path = self.directory / f"{name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"name": name, "actions": actions}, f, indent=2)
        logger.info(f"Saved cycle '{name}' ({len(actions)} actions)")
        return path

    def load(self, name: str) -> Dict:
        path = self.directory / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Cycle not found: {name}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list(self) -> List[str]:
        return sorted(p.stem for p in self.directory.glob("*.json"))

    def delete(self, name: str) -> bool:
        path = self.directory / f"{name}.json"
        if path.exists():
            path.unlink()
            return True
        return False
