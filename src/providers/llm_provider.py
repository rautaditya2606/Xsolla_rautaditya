import json
import re
import httpx
from src.config import config
from src.providers.base import BaseProvider
from src.services.chunker import DiffChunk
from src.models.schemas import Finding

LLM_SYSTEM_PROMPT = """You are an expert AI code reviewer. Analyze the unified diff and return findings strictly as a JSON array of objects matching this schema:
[
  {
    "id": "LLM-001:<path>:<line>",
    "ruleId": "LLM-001",
    "path": "<file_path>",
    "line": <line_number_in_new_file>,
    "severity": "critical" | "high" | "medium" | "low",
    "category": "security" | "correctness" | "performance" | "style",
    "title": "<short_title>",
    "evidence": "<exact_added_line>"
  }
]
Return ONLY valid JSON array with no extra markdown formatting."""

class LLMProvider(BaseProvider):
    async def analyze_chunk(self, chunk: DiffChunk) -> list[Finding]:
        if not config.LLM_API_KEY:
            raise RuntimeError("LLM_API_KEY is not configured on the server")

        combined_diff = "\n".join(f.raw_diff for f in chunk.files)

        headers = {
            "Authorization": f"Bearer {config.LLM_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": config.LLM_MODEL,
            "messages": [
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": f"Review this diff:\n\n{combined_diff}"}
            ],
            "temperature": 0.1
        }

        url = "https://api.openai.com/v1/chat/completions"
        if "groq" in config.LLM_PROVIDER.lower():
            url = "https://api.groq.com/openai/v1/chat/completions"
        elif "together" in config.LLM_PROVIDER.lower():
            url = "https://api.together.xyz/v1/chat/completions"

        async with httpx.AsyncClient(timeout=25.0) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()

                if content.startswith("```"):
                    content = re.sub(r"^```[a-z]*\n?", "", content)
                    content = re.sub(r"\n?```$", "", content)

                raw_list = json.loads(content)
                findings: list[Finding] = []
                for item in raw_list:
                    findings.append(Finding(**item))
                return findings
            except Exception as err:
                raise RuntimeError(f"LLM Provider API request failed: {str(err)}") from err
