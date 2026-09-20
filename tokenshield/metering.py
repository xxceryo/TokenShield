import json
from dataclasses import dataclass

try:
    import tiktoken
except ImportError:  # pragma: no cover - optional runtime fallback
    tiktoken = None


@dataclass(frozen=True)
class ModelPricing:
    input_per_million: float = 0.0
    output_per_million: float = 0.0


class TokenMeter:
    """Provider-neutral token and cost meter with safe, observable fallbacks."""

    def __init__(self, pricing_json: str = ""):
        try:
            raw = json.loads(pricing_json or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("TOKENSHIELD_PRICING_JSON must be valid JSON") from exc
        self.pricing = {
            model: ModelPricing(
                float(values.get("input_per_million", 0)),
                float(values.get("output_per_million", 0)),
            )
            for model, values in raw.items()
            if isinstance(values, dict)
        }

    def _pricing(self, model: str | None) -> ModelPricing:
        if model in self.pricing:
            return self.pricing[model]
        if model:
            for pattern, pricing in self.pricing.items():
                if pattern.endswith("*") and model.startswith(pattern[:-1]):
                    return pricing
        return ModelPricing()

    def count(self, value, model: str | None = None) -> int:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        if tiktoken is not None:
            try:
                encoding = tiktoken.encoding_for_model(model or "gpt-4o-mini")
                return max(1, len(encoding.encode(text)))
            except (KeyError, ValueError):
                pass
        return max(1, (len(text) + 3) // 4)

    def cost(self, model: str | None, input_tokens: int, output_tokens: int = 0) -> float:
        pricing = self._pricing(model)
        return (input_tokens * pricing.input_per_million + output_tokens * pricing.output_per_million) / 1_000_000
