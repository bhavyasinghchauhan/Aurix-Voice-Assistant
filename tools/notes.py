"""Quick note-taking: create, read, and list text notes."""
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from utils.error_handler import ToolExecutionError
from utils.logger import get_logger

logger = get_logger(__name__)

NOTES_DIR = Path(os.path.dirname(os.path.dirname(__file__))) / "notes"


def _ensure_dir() -> Path:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    return NOTES_DIR


async def create_note(content: str, title: Optional[str] = None) -> dict:
    """Save a new note to the notes directory."""
    _ensure_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if title:
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
        filename = f"{ts}_{safe_title.strip()[:40]}.txt"
    else:
        filename = f"{ts}_note.txt"

    path = NOTES_DIR / filename
    path.write_text(content, encoding="utf-8")
    logger.info(f"Note created: {path}")
    return {"file": filename, "path": str(path), "summary": f"Note saved as {filename}"}


async def read_note(filename: str) -> dict:
    """Read a specific note by filename."""
    _ensure_dir()
    path = NOTES_DIR / filename
    if not path.exists():
        matches = list(NOTES_DIR.glob(f"*{filename}*"))
        if matches:
            path = matches[0]
        else:
            raise ToolExecutionError(f"Note not found: {filename}")

    content = path.read_text(encoding="utf-8")
    logger.info(f"Read note: {path.name} ({len(content)} chars)")
    return {"file": path.name, "content": content, "summary": content[:200]}


async def list_notes() -> dict:
    """List all notes, most recent first."""
    _ensure_dir()
    notes: List[dict] = []
    for f in sorted(NOTES_DIR.glob("*.txt"), reverse=True):
        stat = f.stat()
        notes.append({
            "file": f.name,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    logger.info(f"Listed {len(notes)} notes")
    summary = (
        f"{len(notes)} notes: " + ", ".join(n["file"] for n in notes[:5])
        if notes else "No notes yet"
    )
    return {"notes": notes, "count": len(notes), "summary": summary}
