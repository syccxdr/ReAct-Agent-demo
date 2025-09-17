import os
import requests
from typing import Any, Dict, Optional, Tuple
from src.config.logging import logger


class KimiClient:
    """
    Minimal OpenAI-compatible Chat Completions client for Kimi K2.
    Returns text and usage dict: {token_in, token_out}.
    """

    def __init__(self,
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 model: Optional[str] = None,
                 timeout: float = 30.0) -> None:
        self.api_key = api_key or os.getenv("KIMI_API_KEY", "")
        self.base_url = (base_url or os.getenv("KIMI_BASE_URL") or "https://api.moonshot.cn/v1").rstrip("/")
        self.model = model or os.getenv("KIMI_MODEL", "kimi-k2-0905-preview")
        self.timeout = timeout
        if not self.api_key:
            logger.warning("Kimi API key is not set. Set KIMI_API_KEY to enable Kimi provider.")

    def generate(self, prompt: str, temperature: float = 0.3, max_tokens: int = 1024) -> Tuple[str, Dict[str, int]]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            text = ""
            if isinstance(data, dict):
                choices = data.get("choices") or []
                if choices:
                    msg = choices[0].get("message") or {}
                    text = msg.get("content") or ""
            usage = data.get("usage", {}) if isinstance(data, dict) else {}
            token_in = int(usage.get("prompt_tokens", 0))
            token_out = int(usage.get("completion_tokens", 0))
            return text or "", {"token_in": token_in, "token_out": token_out}
        except requests.RequestException as e:
            logger.error("Kimi request failed: %s", e)
            return f"Kimi request failed: {e}", {"token_in": 0, "token_out": 0}
        except Exception as e:
            logger.error("Kimi unexpected error: %s", e)
            return f"Kimi unexpected error: {e}", {"token_in": 0, "token_out": 0}


