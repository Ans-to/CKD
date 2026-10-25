"""Resource introspection: free Colab runtimes are small and get killed abruptly.

Every expensive stage calls these helpers before allocating large downloads so
the pipeline fails fast with an actionable message instead of an OOM kill.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


@dataclass
class SystemInfo:
    cpu_count: int
    mem_total: float
    mem_available: float
    disk_free: float
    disk_total: float
    gpu: str | None = None

    def to_dict(self) -> dict:
        return {
            "cpu_count": self.cpu_count,
            "mem_total_gb": round(self.mem_total / 1e9, 2),
            "mem_available_gb": round(self.mem_available / 1e9, 2),
            "disk_free_gb": round(self.disk_free / 1e9, 2),
            "disk_total_gb": round(self.disk_total / 1e9, 2),
            "gpu": self.gpu,
        }


def _gpu_name() -> str | None:
    try:  # torch is present in Colab but optional for us
        import torch  # type: ignore

        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:
        pass
    return None


def meminfo() -> tuple[float, float]:
    """Return (total, available) bytes for RAM (Linux /proc/meminfo)."""
    try:
        values: dict[str, int] = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                parts = rest.split()
                if parts:
                    values[key.strip()] = int(parts[0]) * 1024
        total = values.get("MemTotal", 0)
        avail = values.get("MemAvailable", values.get("MemFree", 0))
        return float(total), float(avail)
    except Exception:
        pass
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        return float(vm.total), float(vm.available)
    except Exception:
        return 0.0, 0.0


def system_info(path: str | Path = ".") -> SystemInfo:
    total, avail = meminfo()
    usage = shutil.disk_usage(str(path))
    return SystemInfo(
        cpu_count=os.cpu_count() or 1,
        mem_total=total,
        mem_available=avail,
        disk_free=usage.free,
        disk_total=usage.total,
        gpu=_gpu_name(),
    )


class ResourceError(RuntimeError):
    """Raised when a stage cannot safely run in the current runtime."""


def check_disk_space(path: str | Path, needed_bytes: int, *, margin: int = 512 * 1024**2) -> None:
    free = shutil.disk_usage(str(path)).free
    if free < needed_bytes + margin:
        raise ResourceError(
            f"Not enough disk space in {path}: need {human_bytes(needed_bytes)} + "
            f"{human_bytes(margin)} margin, free {human_bytes(free)}. "
            "Free space in Drive/Colab or lower the render quality."
        )


def check_memory(needed_bytes: int, *, note: str = "") -> None:
    total, avail = meminfo()
    if total and avail < needed_bytes:
        raise ResourceError(
            f"Not enough RAM: need ~{human_bytes(needed_bytes)}, available {human_bytes(avail)}. {note} "
            "Restart the Colab runtime and try again with a smaller model/render size."
        )
