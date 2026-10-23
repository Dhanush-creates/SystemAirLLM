"""Model registry: loads config/models.yaml and filters models by hardware profile."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "models.yaml"
CPU_BUDGET_GB = 6.0  # largest model budget used when there is no NVIDIA GPU


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str
    capabilities: tuple[str, ...]
    tier: int
    vram_gb: float
    context: int = 8192
    enabled: bool = True
    escalation_only: bool = False  # too slow to pick first; used only when other models fail
    think: bool = True             # false = switch off the model's hidden reasoning (faster replies)


def detect_budget() -> tuple[float, str]:
    """Memory budget for models on this machine: NVIDIA GPU memory, else half the system RAM."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        return round(max(int(x) for x in out.stdout.split()) / 1024, 1), "NVIDIA GPU"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        import psutil
        # On a CPU a large model fits in memory but answers far too slowly, so the budget is capped
        # to keep the choice to the small models.
        half_ram = psutil.virtual_memory().total / 2**30 / 2
        return round(min(half_ram, CPU_BUDGET_GB), 1), "CPU and system memory (no NVIDIA GPU found)"


class Registry:
    def __init__(self, config: dict, profile: str | None = None):
        self.profile = profile or os.environ.get("WORKBENCH_PROFILE") or config["profile"]
        if self.profile == "auto":
            self.vram_gb, self.device = detect_budget()
        else:
            self.vram_gb, self.device = config["profiles"][self.profile]["vram_gb"], "set by profile"
        if os.environ.get("WORKBENCH_VRAM"):  # manual override, in GB
            self.vram_gb, self.device = float(os.environ["WORKBENCH_VRAM"]), "set by WORKBENCH_VRAM"
        self.providers = config["providers"]
        self.sandbox = config.get("sandbox", "auto")
        self.allow_private_network = config.get("allow_private_network", False)
        self.models = [
            ModelSpec(**{**m, "capabilities": tuple(m["capabilities"])}) for m in config["models"]
        ]

    @classmethod
    def load(cls, path: Path | None = None, profile: str | None = None) -> "Registry":
        """Loads config/models.yaml, or the file named by the WORKBENCH_CONFIG environment variable."""
        path = path or os.environ.get("WORKBENCH_CONFIG") or DEFAULT_CONFIG
        return cls(yaml.safe_load(Path(path).read_text(encoding="utf-8")), profile)

    def usable(self, capability: str) -> list[ModelSpec]:
        """Enabled models with this capability that fit the active profile's VRAM."""
        return [
            m for m in self.models
            if m.enabled and capability in m.capabilities and m.vram_gb <= self.vram_gb
        ]

    def recommended(self, per_capability: int = 2) -> list[ModelSpec]:
        """Models worth installing on this hardware: the largest few that fit, per capability."""
        out: list[ModelSpec] = []
        for capability in ("general", "code", "vision"):
            fits = [m for m in self.usable(capability)
                    if not m.escalation_only and self.providers[m.provider]["type"] == "openai"]
            for m in sorted(fits, key=lambda m: -m.tier)[:per_capability]:
                if m not in out:
                    out.append(m)
        return out
