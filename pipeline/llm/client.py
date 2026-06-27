"""
vLLM Client Wrapper for Latinos.org Pipeline.

Connects to the local vLLM instance (qwen3.5-27b on RTX Pro 6000 Blackwell)
via the OpenAI-compatible API endpoint.

STRICT RULE: The sampling parameters below are dialed in by the operator and
must NOT be changed. They match the production vLLM configuration.
"""

import logging
import time
from typing import Optional, Dict, Any

import httpx

from config import VLLM_BASE_URL, VLLM_MODEL

logger = logging.getLogger(__name__)

# =============================================================================
# SAMPLING PARAMETERS — DO NOT MODIFY
# These match the operator's production vLLM configuration.
# =============================================================================
SAMPLING_PARAMS: Dict[str, Any] = {
    "temperature": 1.0,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "presence_penalty": 0.0,
    "repetition_penalty": 1.0,
    "max_tokens": 8196,
    # Chain-of-thought reasoning (used by qwen3.5-27b)
    "thinking_token_budget": 480,
    "reasoning_effort": "low",
    "chat_template_kwargs": {"preserve_thinking": False},
}
# =============================================================================


async def chat_completion(
    system_prompt: str,
    user_prompt: str,
    timeout: float = 180.0,
) -> Optional[str]:
    """
    Send a chat completion request to vLLM.

    Uses the fixed sampling parameters defined above — these are NOT configurable.

    Returns the response content string, or None on error.
    """
    payload = {
        "model": VLLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        **SAMPLING_PARAMS,
    }

    url = f"{VLLM_BASE_URL}/chat/completions"

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
            )
        response.raise_for_status()

        elapsed = (time.monotonic() - start) * 1000
        data = response.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content")

        # Fallback to reasoning field if content is empty
        if not content:
            content = msg.get("reasoning", "")

        content = content.strip() if content else ""
        tokens = data.get("usage", {}).get("completion_tokens", 0)
        logger.debug(f"[vLLM] {elapsed:.0f}ms, {tokens} tokens")

        return content

    except httpx.ConnectError:
        logger.error(f"[vLLM] Cannot connect to {VLLM_BASE_URL}. Is vLLM running?")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"[vLLM] HTTP {e.response.status_code}: {e.response.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"[vLLM] Error: {e}")
        return None


async def check_health() -> bool:
    """Check if the vLLM endpoint is reachable and the model is loaded."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{VLLM_BASE_URL}/models")
        if response.status_code == 200:
            data = response.json()
            models = [m["id"] for m in data.get("data", [])]
            logger.info(f"[vLLM] Connected. Available models: {models}")
            return len(models) > 0
        return False
    except Exception:
        return False
