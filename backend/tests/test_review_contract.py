import json

import pytest

from app.review_contract import fingerprint, validate_output

SOURCE = {
    "title": "上传",
    "description": "用户上传文件，系统快速处理。",
    "acceptance_criteria": "",
    "version": 1,
}
FINDING = {
    "category": "acceptance",
    "field": "description",
    "quote": "快速处理",
    "problem": "缺少可验证的响应时间",
    "question": "可接受的处理时间是多少？",
}


def test_valid_grounding_and_no_findings():
    assert validate_output(json.dumps({"findings": [FINDING]}), SOURCE) == [FINDING]
    assert validate_output('{"findings":[]}', SOURCE) == []


@pytest.mark.parametrize(
    "change",
    [
        {"quote": "不存在的原文"},
        {"field": "title"},
        {"category": "score"},
        {"question": " "},
        {"extra": "not allowed"},
    ],
)
def test_reject_unsupported_or_ungrounded(change):
    with pytest.raises(ValueError):
        validate_output(json.dumps({"findings": [FINDING | change]}), SOURCE)


def test_duplicate_limit_and_version_fingerprint():
    with pytest.raises(ValueError):
        validate_output(json.dumps({"findings": [FINDING, FINDING]}), SOURCE)
    with pytest.raises(ValueError):
        validate_output(json.dumps({"findings": [FINDING] * 9}), SOURCE)
    assert fingerprint(SOURCE) != fingerprint(SOURCE | {"version": 2})
