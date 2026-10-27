import re
from dataclasses import dataclass, field
from typing import Literal

# things that usually mean the answer needs real code understanding
CODE_PATTERN = re.compile(
    r"```|^\s*(def|class|function|import|from|#include|public|const|let|SELECT|CREATE)\b|=>|\{\s*$",
    re.MULTILINE | re.IGNORECASE,
)
NUMBERED_STEP = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)


@dataclass(frozen=True)
class RouterRules:
    simple_model: str
    complex_model: str
    threshold: int = 3  # score at or above this goes to the complex model
    long_prompt_chars: int = 800
    very_long_prompt_chars: int = 3000
    long_history_messages: int = 12
    keywords: tuple[str, ...] = field(default_factory=tuple)
    max_keyword_points: int = 2


@dataclass(frozen=True)
class RouteDecision:
    model: str
    tier: Literal["simple", "complex"]
    score: int
    reasons: tuple[str, ...]

    @property
    def reason(self) -> str:
        return "; ".join(self.reasons) if self.reasons else "short, simple prompt"


class ModelRouter:
    """Rule-based router: cheap model for easy prompts, strong model for hard ones."""

    def __init__(self, rules: RouterRules) -> None:
        self.rules = rules

    def score(self, prompt: str, history_messages: int = 0) -> tuple[int, list[str]]:
        r = self.rules
        score = 0
        reasons: list[str] = []

        if len(prompt) >= r.very_long_prompt_chars:
            score += 2
            reasons.append(f"very long prompt ({len(prompt)} chars)")
        elif len(prompt) >= r.long_prompt_chars:
            score += 1
            reasons.append(f"long prompt ({len(prompt)} chars)")

        if CODE_PATTERN.search(prompt):
            score += 2
            reasons.append("contains code")

        lowered = prompt.lower()
        hits = [k for k in r.keywords if k in lowered]
        if hits:
            score += min(len(hits), r.max_keyword_points)
            reasons.append("reasoning keywords: " + ", ".join(hits[:4]))

        if prompt.count("?") >= 3:
            score += 1
            reasons.append("multiple questions")

        if len(NUMBERED_STEP.findall(prompt)) >= 3:
            score += 1
            reasons.append("multi-step instructions")

        if history_messages >= r.long_history_messages:
            score += 1
            reasons.append(f"long conversation ({history_messages} messages)")

        return score, reasons

    def route(self, prompt: str, history_messages: int = 0) -> RouteDecision:
        score, reasons = self.score(prompt, history_messages)
        if score >= self.rules.threshold:
            return RouteDecision(self.rules.complex_model, "complex", score, tuple(reasons))
        return RouteDecision(self.rules.simple_model, "simple", score, tuple(reasons))
