"""Explicit server-owned connections; no client-supplied URLs or credentials."""

import json
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from .config import get_settings
from .review_contract import SYSTEM_PROMPT, ReviewOutput, validate_output


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


def response_format(config):
    # Vendor-specific strict mode is scoped to documented Groq models.
    if config["url"] == "https://api.groq.com/openai/v1" and config["model"] in {
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
    }:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "requirement_findings",
                "strict": True,
                "schema": provider_schema(),
            },
        }
    return {"type": "json_object"}


def provider_schema():
    """Send a simple inline schema; length/count bounds stay in local validation."""
    schema = ReviewOutput.model_json_schema()
    definitions = schema.get("$defs", {})

    def simplify(value):
        if isinstance(value, list):
            return [simplify(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            return simplify(definitions[value["$ref"].split("/")[-1]])
        return {
            key: simplify(item)
            for key, item in value.items()
            if key not in {"$defs", "title", "minLength", "maxLength", "maxItems"}
        }

    return simplify(schema)


def generate(source, config):
    headers = {"Authorization": "Bearer " + config["key"]} if config["key"] else {}
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(source, ensure_ascii=False)},
        ],
        "response_format": response_format(config),
        "max_tokens": 4096,
        "stream": False,
    }
    if payload["response_format"]["type"] == "json_schema":
        payload["max_completion_tokens"] = payload.pop("max_tokens")
        payload["include_reasoning"] = False
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
                    raise ReviewFailure(f"provider_http_{response.status_code}")
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
        try:
            findings = validate_output(choice["message"]["content"], source)
        except ValidationError:
            raise ReviewFailure("invalid_schema") from None
        except ValueError as exc:
            code = str(exc)
            raise ReviewFailure(
                code
                if code in {"ungrounded_quote", "duplicate_finding", "output_too_large"}
                else "invalid_output"
            ) from None
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
