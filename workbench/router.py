"""Router: classify a task, then pick a model by capability, complexity and hardware."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .registry import ModelSpec, Registry

CODE_RE = re.compile(
    r"\b(code|python|script|function|bug|debug|sql|compile|unit tests?|program|regex|refactor|algorithm)\b", re.I
)
COMPLEX_RE = re.compile(
    r"\b(draft|analy|report|plan|compar|calculat|design|review|approval|summar|step by step|tests?|verif|present|slide|spreadsheet|excel|document|powerpoint)\w*", re.I
)


class NoModelAvailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Task:
    text: str
    attachments: tuple[str, ...] = ()
    context: str = ""  # earlier turns of the same conversation, already formatted for a prompt


@dataclass
class Decision:
    capability: str
    complexity: str              # "low" | "high"
    model: ModelSpec
    candidates: list[ModelSpec]  # in preference order
    reason: str


def classify(task: Task) -> tuple[str, str]:
    # Attachments are read by the input layer (vision model for scans and images) before
    # the loop starts, so the driving model is chosen from the request text alone.
    capability = "code" if CODE_RE.search(task.text) else "general"
    is_complex = bool(task.attachments) or len(task.text) > 300 or bool(COMPLEX_RE.search(task.text))
    return capability, "high" if is_complex else "low"


class Router:
    def __init__(self, registry: Registry, providers: dict):
        self.registry = registry
        self.providers = providers

    def _available(self, m: ModelSpec) -> bool:
        return self.providers[m.provider].available(m.id)

    def route(self, task: Task) -> Decision:
        return self.route_for(*classify(task))

    def route_for(self, capability: str, complexity: str) -> Decision:
        # Only the two largest models that fit are first choices, so a tiny model installed on a
        # big machine is not used. Complex task: the largest. Simple task: the smaller of the two.
        # Anything smaller stays in the list as a backup.
        def order(models):
            by_size = sorted(models, key=lambda m: -m.tier)
            top, rest = by_size[:2], by_size[2:]
            return (top if complexity == "high" else top[::-1]) + rest

        candidates = order(self.registry.usable(capability))
        # General models back up a specialist that is missing or down.
        candidates += [m for m in order(self.registry.usable("general")) if m not in candidates]
        candidates.sort(key=lambda m: m.escalation_only)  # stable: slow escalation-only models go last
        for m in candidates:
            if self._available(m):
                backup = "" if capability in m.capabilities else f" (no {capability} model available, using general)"
                reason = (
                    f"{capability} task, {complexity} complexity{backup}: "
                    f"{'largest' if complexity == 'high' else 'lighter'} available model "
                    f"within {self.registry.vram_gb} GB ({self.registry.profile} profile)"
                )
                return Decision(capability, complexity, m, candidates, reason)
        raise NoModelAvailable(
            f"no model available for '{capability}' on profile '{self.registry.profile}'. "
            f"Tried: {[m.id for m in candidates] or 'none configured'}"
        )

    def next_model(self, d: Decision, tried: set[str], bigger_than: int | None = None) -> ModelSpec | None:
        """Next untried candidate. With bigger_than, only models of a higher tier (escalation)."""
        pool = [m for m in d.candidates if m.id not in tried]
        if bigger_than is not None:
            pool = sorted((m for m in pool if m.tier > bigger_than), key=lambda m: m.tier)
        return next((m for m in pool if self._available(m)), None)
