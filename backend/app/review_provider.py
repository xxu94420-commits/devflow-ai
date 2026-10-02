"""Explicit server-owned connections; no client-supplied URLs or credentials."""

import json
from urllib.parse import urlsplit

import httpx

from .config import get_settings
from .review_contract import SYSTEM_PROMPT, validate_output


class ReviewFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def connection(provider):
    settings = get_settings()
    if provider == "cloud":
        url, model, key = (
            settings.review_api_base_url,
            settings.review_model,
            settings.review_api_key,
        )
        enabled = bool(url and model and key)
    elif provider == "ollama":
        url, model, key = (
            settings.review_ollama_base_url,
            settings.review_ollama_model,
            "",
        )
        enabled = bool(settings.review_ollama_enabled and model)
    else:
        raise ReviewFailure("not_configured")
    parsed = urlsplit(url)
    valid = (
        bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
        and (
            parsed.scheme == "https"
            or (
                provider == "ollama"
                and parsed.scheme == "http"
                and parsed.hostname
                in {"127.0.0.1", "localhost", "host.docker.internal"}
            )
        )
    )
    if not enabled or not valid or len(model) > 200 or len(url) > 300:
        raise ReviewFailure("not_configured")
    return {"url": url.rstrip("/"), "model": model, "key": key}


def connections():
    result = []
    for ident, label in [("cloud", "管理员配置的云端模型"), ("ollama", "本地 Ollama")]:
        try:
            config = connection(ident)
            result.append(
                {
                    "id": ident,
                    "label": label,
                    "configured": True,
                    "model": config["model"],
                    "destination": config["url"],
                }
            )
        except (ReviewFailure, ValueError):
            result.append(
                {
                    "id": ident,
                    "label": label,
                    "configured": False,
                    "model": "",
                    "destination": "",
                }
            )
    return result


def generate(source, config):
    headers = {"Authorization": "Bearer " + config["key"]} if config["key"] else {}
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(source, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 4096,
        "stream": False,
    }
    try:
        # One attempt only: retrying a timed-out billable request may double charge.
        with httpx.Client(timeout=httpx.Timeout(90, connect=10)) as client:
            with client.stream(
                "POST",
                config["url"] + "/chat/completions",
                headers=headers,
                json=payload,
                follow_redirects=False,
            ) as response:
                if response.status_code == 429:
                    raise ReviewFailure("rate_limited")
                if response.status_code in (401, 403):
                    raise ReviewFailure("authentication")
                if response.status_code != 200:
                    raise ReviewFailure("provider_error")
                parts, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 131072:
                        raise ReviewFailure("invalid_output")
                    parts.append(chunk)
                data = json.loads(b"".join(parts))
        choice = data["choices"][0]
        if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
            raise ReviewFailure("incomplete_output")
        findings = validate_output(choice["message"]["content"], source)
        usage = {
            k: v
            for k, v in (data.get("usage") or {}).items()
            if k in {"prompt_tokens", "completion_tokens", "total_tokens"}
            and type(v) is int
            and v >= 0
        }
        return findings, usage
    except httpx.TimeoutException:
        raise ReviewFailure("timeout") from None
    except httpx.HTTPError:
        raise ReviewFailure("network") from None
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ReviewFailure("invalid_output") from None
