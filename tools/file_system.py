"""File system operations."""
import os
from pathlib import Path
from typing import List, Optional

from utils.error_handler import ToolExecutionError
from utils.logger import get_logger

logger = get_logger(__name__)


async def file_search(
    filename: str, directory: Optional[str] = None, max_results: int = 25
) -> dict:
    """Recursively search for files matching a pattern."""
    root = Path(directory).expanduser() if directory else Path.home()
    if not root.exists():
        raise ToolExecutionError(f"Directory does not exist: {root}")

    matches: List[str] = []
    pattern = filename.lower()
    for path in root.rglob("*"):
        try:
            if pattern in path.name.lower():
                matches.append(str(path))
                if len(matches) >= max_results:
                    break
        except (PermissionError, OSError):
            continue

    return {"query": filename, "directory": str(root), "matches": matches}


async def delete_file(path: str) -> dict:
    """Delete a single file. Refuses directories."""
    target = Path(path).expanduser()
    if not target.exists():
        raise ToolExecutionError(f"File not found: {target}")
    if target.is_dir():
        raise ToolExecutionError(f"Refusing to delete directory: {target}")
    try:
        target.unlink()
        logger.warning(f"Deleted file: {target}")
        return {"path": str(target), "deleted": True}
    except OSError as e:
        raise ToolExecutionError(f"Failed to delete {target}: {e}") from e


async def read_file(path: str, max_bytes: int = 100_000) -> dict:
    """Read up to max_bytes of a text file."""
    target = Path(path).expanduser()
    if not target.is_file():
        raise ToolExecutionError(f"Not a file: {target}")
    with open(target, "r", encoding="utf-8", errors="replace") as f:
        content = f.read(max_bytes)
    return {"path": str(target), "content": content, "size": os.path.getsize(target)}
