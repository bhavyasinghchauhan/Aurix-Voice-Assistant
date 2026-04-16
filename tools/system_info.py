"""System information: CPU, RAM, disk, battery."""
import platform
from typing import Optional

import psutil

from utils.logger import get_logger

logger = get_logger(__name__)


async def get_system_info() -> dict:
    """Return a snapshot of system resource usage."""
    cpu_pct = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    info = {
        "cpu_percent": cpu_pct,
        "ram_total_gb": round(mem.total / (1024 ** 3), 1),
        "ram_used_gb": round(mem.used / (1024 ** 3), 1),
        "ram_percent": mem.percent,
        "disk_total_gb": round(disk.total / (1024 ** 3), 1),
        "disk_used_gb": round(disk.used / (1024 ** 3), 1),
        "disk_percent": disk.percent,
        "platform": platform.system(),
    }

    battery = psutil.sensors_battery()
    if battery is not None:
        info["battery_percent"] = battery.percent
        info["battery_plugged"] = battery.power_plugged
    else:
        info["battery_percent"] = None
        info["battery_plugged"] = None

    parts = [
        f"CPU {cpu_pct}%",
        f"RAM {mem.percent}% ({info['ram_used_gb']}/{info['ram_total_gb']} GB)",
        f"Disk {disk.percent}% ({info['disk_used_gb']}/{info['disk_total_gb']} GB)",
    ]
    if battery is not None:
        plug = "plugged in" if battery.power_plugged else "on battery"
        parts.append(f"Battery {battery.percent}% ({plug})")

    info["summary"] = ", ".join(parts)
    logger.info(f"System info: {info['summary']}")
    return info
