import os
import time
from typing import Protocol, TypeVar

from pydantic import BaseModel

from . import config
from .usage import UsageTracker

T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    def generate(self, model: str, system: str, contents: str, schema: type[T], label: str = "") -> T: ...


class GeminiLLM:
    def __init__(self, api_key: str | None = None):
        from google import genai
        self._genai = genai
        self.client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"])
        self.calls = 0
        self.usage = UsageTracker(log_path=config.USAGE_LOG)

    def generate(self, model: str, system: str, contents: str, schema: type[T], label: str = "") -> T:
        from google.genai import types
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            response_mime_type="application/json",
            response_schema=schema,
        )
        last: Exception | None = None
        for attempt in range(3):
            try:
                self.calls += 1
                resp = self.client.models.generate_content(model=model, contents=contents, config=cfg)
                u = resp.usage_metadata
                if u is not None:
                    # Flash models can spend hidden "thinking" tokens; Google bills those as
                    # output tokens, so they must be added to completion_tokens or cost is
                    # undercounted even though total_tokens (used for the raw count) already
                    # includes them.
                    self.usage.record(label or "unlabeled", model,
                                       prompt_tokens=u.prompt_token_count or 0,
                                       completion_tokens=(u.candidates_token_count or 0) + (u.thoughts_token_count or 0),
                                       total_tokens=u.total_token_count or 0)
                return schema.model_validate_json(resp.text)
            except Exception as e:  # transient API / parse errors
                last = e
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"LLM call failed: {last}")
