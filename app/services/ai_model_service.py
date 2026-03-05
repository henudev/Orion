from __future__ import annotations

import json
from typing import Callable
from urllib import error, request

from app.models.model_config import ModelConfig


class AIModelError(RuntimeError):
    pass


def _normalize_base_url(base_url: str) -> str:
    return base_url.strip().rstrip("/")


def _resolve_openai_endpoint(base_url: str) -> str:
    normalized = _normalize_base_url(base_url)
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _resolve_ollama_endpoint(base_url: str) -> str:
    normalized = _normalize_base_url(base_url)
    if normalized.endswith("/api/chat"):
        return normalized
    return f"{normalized}/api/chat"


def _prefer_openai_compat(base_url: str) -> bool:
    normalized = _normalize_base_url(base_url)
    return normalized.endswith("/v1") or "/v1/" in normalized or normalized.endswith("/chat/completions")


def _strip_markdown_fence(text: str) -> str:
    content = text.strip()
    if not content.startswith("```"):
        return content

    lines = content.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _http_post_json(url: str, payload: dict, headers: dict[str, str], timeout: int = 120) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url=url, data=body, method="POST")
    for key, value in headers.items():
        req.add_header(key, value)

    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AIModelError(f"HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise AIModelError(f"request failed: {exc.reason}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIModelError(f"invalid json response: {raw[:300]}") from exc
    if not isinstance(data, dict):
        raise AIModelError("invalid response payload")
    return data


def _extract_openai_content(data: dict) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AIModelError("openai response missing choices")

    first = choices[0]
    if not isinstance(first, dict):
        raise AIModelError("openai response choice invalid")

    message = first.get("message")
    if not isinstance(message, dict):
        raise AIModelError("openai response missing message")

    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    text_parts.append(text)
        if text_parts:
            return "\n".join(text_parts)
    raise AIModelError("openai response missing content")


def _extract_ollama_content(data: dict) -> str:
    message = data.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
    response = data.get("response")
    if isinstance(response, str) and response.strip():
        return response
    raise AIModelError("ollama response missing content")


def _call_openai_like(config: ModelConfig, messages: list[dict[str, str]], purpose: str) -> str:
    endpoint = _resolve_openai_endpoint(config.base_url)
    payload: dict = {
        "model": config.model_name,
        "messages": messages,
        "stream": False,
    }
    if config.temperature is not None:
        payload["temperature"] = config.temperature
    if config.max_tokens is not None:
        payload["max_tokens"] = config.max_tokens

    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    data = _http_post_json(endpoint, payload, headers)
    content = _extract_openai_content(data)
    if not content.strip():
        raise AIModelError(f"{purpose} returned empty content")
    return content


def _call_ollama_native(config: ModelConfig, messages: list[dict[str, str]], purpose: str) -> str:
    endpoint = _resolve_ollama_endpoint(config.base_url)
    payload: dict = {
        "model": config.model_name,
        "messages": messages,
        "stream": False,
    }
    options: dict = {}
    if config.temperature is not None:
        options["temperature"] = config.temperature
    if config.max_tokens is not None:
        options["num_predict"] = config.max_tokens
    if options:
        payload["options"] = options

    headers = {"Content-Type": "application/json"}
    data = _http_post_json(endpoint, payload, headers)
    content = _extract_ollama_content(data)
    if not content.strip():
        raise AIModelError(f"{purpose} returned empty content")
    return content


def _call_ollama(config: ModelConfig, messages: list[dict[str, str]], purpose: str) -> str:
    # Compatibility mode:
    # 1) Native Ollama API: /api/chat
    # 2) OpenAI-compatible endpoint: /v1/chat/completions
    # The order is inferred from base_url.
    use_openai_first = _prefer_openai_compat(config.base_url)
    attempts: list[tuple[str, Callable[[ModelConfig, list[dict[str, str]], str], str]]] = (
        [("openai-compatible", _call_openai_like), ("ollama-native", _call_ollama_native)]
        if use_openai_first
        else [("ollama-native", _call_ollama_native), ("openai-compatible", _call_openai_like)]
    )

    errors: list[str] = []
    for label, fn in attempts:
        try:
            return fn(config, messages, purpose)
        except AIModelError as exc:
            errors.append(f"{label}: {exc}")

    raise AIModelError("ollama provider request failed; " + " | ".join(errors))


def chat_completion(config: ModelConfig, messages: list[dict[str, str]], purpose: str) -> str:
    if config.provider == "openai":
        return _call_openai_like(config, messages, purpose)
    if config.provider == "ollama":
        return _call_ollama(config, messages, purpose)
    raise AIModelError(f"unsupported provider: {config.provider}")


def generate_dockerfile(config: ModelConfig, requirement: str) -> str:
    system_prompt = (
        "You are a senior containerization engineer. "
        "Return ONLY the final Dockerfile text, without markdown code fences or any explanation."
    )
    user_prompt = (
        "请根据以下构建要求生成可直接用于生产构建的 Dockerfile。\n"
        "要求如下：\n"
        f"{requirement.strip()}\n\n"
        "补充规则：\n"
        "1) 如果能用多阶段构建则优先使用。\n"
        "2) 安装依赖时尽量利用缓存层。\n"
        "3) 最终镜像尽量精简。\n"
        "4) 仅输出 Dockerfile 内容，不要解释。"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    content = chat_completion(config, messages, purpose="dockerfile generation")
    cleaned = _strip_markdown_fence(content)
    if "FROM " not in cleaned and not cleaned.startswith("FROM"):
        raise AIModelError("model response is not a valid Dockerfile (missing FROM)")
    return cleaned


def test_model_connection(config: ModelConfig) -> tuple[bool, str]:
    messages = [
        {"role": "system", "content": "You are a concise assistant."},
        {"role": "user", "content": "Reply with OK only."},
    ]
    try:
        output = chat_completion(config, messages, purpose="model connection test")
    except AIModelError as exc:
        return False, str(exc)
    return True, f"model reachable, reply: {output.strip()[:80]}"
