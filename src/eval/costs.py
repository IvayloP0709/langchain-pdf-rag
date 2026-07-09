from typing import Optional

from langchain_community.callbacks.manager import get_openai_callback

# USD per 1M tokens: (input, output). get_openai_callback's built-in pricing table
# lags on newer models, so this covers the gap. Update as OpenAI pricing changes.
PRICING_PER_1M = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
}


def estimate_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    pricing = PRICING_PER_1M.get(model)
    if pricing is None:
        return 0.0
    input_rate, output_rate = pricing
    return (prompt_tokens / 1_000_000) * input_rate + (completion_tokens / 1_000_000) * output_rate


class CostTracker:
    """Context manager tracking OpenAI token usage/cost for the LLM calls made inside it,
    via get_openai_callback(). Falls back to a hardcoded pricing table when the callback's
    own cost calculation reports zero for an unrecognized model."""

    def __init__(self, model: Optional[str] = None):
        self.model = model
        self._cb_ctx = None
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.cost_usd = 0.0

    def __enter__(self) -> "CostTracker":
        self._cb_ctx = get_openai_callback()
        self._cb = self._cb_ctx.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self._cb_ctx.__exit__(exc_type, exc_val, exc_tb)

        self.prompt_tokens = self._cb.prompt_tokens
        self.completion_tokens = self._cb.completion_tokens
        self.total_tokens = self._cb.total_tokens
        self.cost_usd = self._cb.total_cost

        if self.cost_usd == 0 and self.total_tokens > 0 and self.model:
            self.cost_usd = estimate_cost(self.prompt_tokens, self.completion_tokens, self.model)

        return False

    def as_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
        }
