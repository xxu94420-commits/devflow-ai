import json
from uuid import uuid4

import httpx
import pytest

from app import requirement_reviews as reviews
from app import review_provider
from app.config import get_settings


def requirement(client):
    p = client.post(
        "/api/projects", json={"name": "Review fixture", "repository": "fixture/review"}
    ).json()
    return client.post(
        "/api/requirements",
        json={
            "project_id": p["id"],
            "title": "上传文件",
            "description": "快速处理文件",
        },
    ).json()


def enable(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "review_api_base_url", "https://provider.example/v1")
    monkeypatch.setattr(settings, "review_api_key", "fixture-secret")
    monkeypatch.setattr(settings, "review_model", "fixture-model")


def request():
    return {
        "expected_version": 1,
        "provider": "cloud",
        "request_key": str(uuid4()),
        "consent": True,
    }


FINDING = {
    "category": "acceptance",
    "field": "description",
    "quote": "快速",
    "problem": "时间标准不明确",
    "question": "处理时限是多少？",
}


def test_review_decision_revision_and_stale(client, monkeypatch):
    enable(monkeypatch)
    calls = []

    def fake(source, config):
        calls.append(source)
        return [FINDING], {"total_tokens": 42}

    monkeypatch.setattr(reviews, "generate", fake)
    req = requirement(client)
    path = f"/api/requirements/{req['id']}/reviews"
    data = request()
    result = client.post(path, json=data).json()
    assert result["status"] == "succeeded"
    assert client.post(path, json=data).json()["id"] == result["id"]
    assert len(calls) == 1
    assert "fixture-secret" not in client.get("/api/review/connections").text
    decision = f"/api/requirement-reviews/{result['id']}/findings/0/decision"
    assert (
        client.post(
            decision, json={"decision": "accepted", "reason": "确认需要澄清"}
        ).status_code
        == 201
    )
    assert (
        client.post(
            decision, json={"decision": "rejected", "reason": "不能覆盖历史"}
        ).status_code
        == 409
    )
    assert client.get(path).json()["requirement"]["description"] == "快速处理文件"
    edit = {
        "project_id": req["project_id"],
        "title": req["title"],
        "description": "每个文件在10秒内处理",
        "expected_version": 1,
        "revision_reason": "明确处理时间",
    }
    response = client.put(f"/api/requirements/{req['id']}", json=edit)
    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert client.put(f"/api/requirements/{req['id']}", json=edit).status_code == 409
    history = client.get(path).json()
    assert history["reviews"][0]["stale"]
    assert len(history["revisions"]) == 2
    assert (
        client.post(
            decision, json={"decision": "accepted", "reason": "old"}
        ).status_code
        == 409
    )
    assert client.post(path, json=request()).status_code == 409
    task = client.post(
        "/api/tasks",
        json={
            "project_id": req["project_id"],
            "requirement_id": req["id"],
            "title": "实现上传",
            "task_type": "功能开发",
            "estimated_hours": 2,
        },
    )
    assert task.status_code == 201
    assert client.get(path).json()["tasks"][0]["id"] == task.json()["id"]


def test_not_configured_consent_mode_isolation_and_failures(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "review_api_key", "")
    req = requirement(client)
    path = f"/api/requirements/{req['id']}/reviews"
    assert client.post(path, json=request()).status_code == 503
    assert client.get(path).json()["reviews"] == []
    assert client.post(path, json=request() | {"consent": False}).status_code == 422
    assert client.get("/api/requirements?mode=demo").json() == []
    assert len(client.get("/api/requirements?mode=live").json()) == 1
    enable(monkeypatch)

    def failed(*_):
        raise review_provider.ReviewFailure("timeout")

    monkeypatch.setattr(reviews, "generate", failed)
    result = client.post(path, json=request()).json()
    assert result["status"] == "failed" and result["findings"] == []
    assert result["error_code"] == "timeout"
    assert client.post(path, json=request()).status_code == 429


@pytest.mark.parametrize(
    "variant,code",
    [
        ("valid", None),
        ("429", "rate_limited"),
        ("401", "authentication"),
        ("500", "provider_http_500"),
        ("redirect", "provider_http_302"),
        ("timeout", "timeout"),
        ("invalid", "invalid_schema"),
        ("ungrounded", "ungrounded_quote"),
        ("truncated", "incomplete_output"),
    ],
)
def test_provider_contract(monkeypatch, variant, code):
    original = httpx.Client

    def handler(req):
        assert str(req.url) == "https://provider.example/v1/chat/completions"
        assert req.headers["authorization"] == "Bearer fixture-secret"
        payload = json.loads(req.content)
        assert payload["messages"][0]["role"] == "system"
        if variant.isdigit():
            return httpx.Response(int(variant), text="fixture-secret must not appear")
        if variant == "redirect":
            return httpx.Response(302, headers={"location": "https://other.example"})
        if variant == "timeout":
            raise httpx.ReadTimeout("fixture-secret", request=req)
        finding = FINDING | ({"quote": "invented"} if variant == "ungrounded" else {})
        content = (
            "not json" if variant == "invalid" else json.dumps({"findings": [finding]})
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length" if variant == "truncated" else "stop",
                        "message": {"content": content},
                    }
                ],
                "usage": {"total_tokens": 30, "secret": "hidden"},
            },
        )

    monkeypatch.setattr(
        review_provider.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    source = {
        "title": "上传",
        "description": "快速处理文件",
        "acceptance_criteria": "",
        "version": 1,
    }
    config = {
        "url": "https://provider.example/v1",
        "key": "fixture-secret",
        "model": "fixture",
    }
    if code:
        with pytest.raises(review_provider.ReviewFailure) as failure:
            review_provider.generate(source, config)
        assert str(failure.value) == code
    else:
        findings, usage = review_provider.generate(source, config)
        assert findings == [FINDING] and usage == {"total_tokens": 30}


def test_connection_validation_and_ollama(monkeypatch):
    enable(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(
        settings, "review_api_base_url", "https://user:password@provider.example/v1"
    )
    assert not review_provider.connections()[0]["configured"]
    monkeypatch.setattr(settings, "review_ollama_enabled", True)
    monkeypatch.setattr(settings, "review_ollama_model", "local-fixture")
    assert review_provider.connection("ollama")["key"] == ""
    monkeypatch.setattr(
        settings, "review_ollama_base_url", "http://untrusted.example/v1"
    )
    with pytest.raises(review_provider.ReviewFailure):
        review_provider.connection("ollama")


def test_groq_strict_format_is_scoped_and_matches_contract():
    config = {"url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-20b"}
    fmt = review_provider.response_format(config)
    assert fmt["type"] == "json_schema"
    schema = fmt["json_schema"]["schema"]
    assert fmt["json_schema"]["strict"] is True
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["findings"]
    finding = schema["properties"]["findings"]["items"]
    assert set(finding["required"]) == {
        "category",
        "field",
        "quote",
        "problem",
        "question",
    }
    assert finding["additionalProperties"] is False
    assert review_provider.response_format(
        config | {"url": "https://other.example/v1"}
    ) == {"type": "json_object"}
    assert review_provider.response_format(config | {"model": "other-model"}) == {
        "type": "json_object"
    }


def test_groq_schema_keeps_local_bounds():
    from app.review_contract import validate_output

    schema = review_provider.provider_schema()
    serialized = json.dumps(schema)
    assert "$ref" not in serialized and "$defs" not in serialized
    assert "minLength" not in serialized and "maxLength" not in serialized
    with pytest.raises(ValueError):
        validate_output(
            json.dumps({"findings": [FINDING] * 9}), {"description": "快速处理文件"}
        )
    assert schema["properties"]["findings"]["items"]["properties"]["category"][
        "enum"
    ] == ["ambiguity", "acceptance", "boundary", "exception", "conflict"]
