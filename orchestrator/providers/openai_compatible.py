import json

import httpx

from orchestrator.models import RequirementAnalysis
from orchestrator.providers.base import AIProvider


class OpenAICompatibleProvider(AIProvider):
    """Optional real-model adapter (AI_PROVIDER=openai). Any error is retried, then the
    orchestrator falls back to the deterministic provider."""

    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def analyze_requirement(self, requirement: str, scenario: str) -> RequirementAnalysis:
        schema = json.dumps(RequirementAnalysis.model_json_schema())
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a cautious requirements analyst. Analyse only; "
                        "never propose production deployment. Reply with JSON matching: " + schema,
                    },
                    {
                        "role": "user",
                        "content": f"Scenario: {scenario}\nRequirement: {requirement}",
                    },
                ],
            },
            timeout=30,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return RequirementAnalysis.model_validate_json(content)
