"""Bounded JUnit evidence parsing. Raw XML/logs are never persisted."""

import hashlib
import io
import json
import re
import zipfile
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

MAX_ARCHIVE = 2 * 1024 * 1024
MAX_EXPANDED = 8 * 1024 * 1024
MAX_CASES = 100000


class EvidenceError(ValueError):
    pass


def parse_junit(data: bytes):
    if len(data) > MAX_EXPANDED:
        raise EvidenceError("JUnit超过大小限制")
    try:
        root = fromstring(data, forbid_dtd=True)
    except (ParseError, DefusedXmlException, ValueError):
        raise EvidenceError("JUnit格式无效或包含禁止的XML实体") from None
    tag = lambda element: element.tag.rsplit("}", 1)[-1]  # noqa: E731
    if tag(root) not in {"testsuite", "testsuites"}:
        raise EvidenceError("JUnit根节点必须为testsuite/testsuites")
    counts = dict(passed=0, failed=0, errors=0, skipped=0)
    cases = [element for element in root.iter() if tag(element) == "testcase"]
    if len(cases) > MAX_CASES:
        raise EvidenceError("JUnit用例数量超过上限")
    if not cases and any(element.get("tests", "0") != "0" for element in root.iter()):
        raise EvidenceError("只有汇总属性，没有可核验testcase")
    for case in cases:
        states = {tag(child) for child in case}
        outcome = (
            "errors"
            if "error" in states
            else (
                "failed"
                if "failure" in states
                else "skipped" if "skipped" in states else "passed"
            )
        )
        counts[outcome] += 1
    return counts


def parse_bundle(content: bytes):
    if len(content) > MAX_ARCHIVE:
        raise EvidenceError("压缩报告超过2MiB上限")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            files = archive.infolist()
            names = [f.filename for f in files]
            if (
                len(files) > 25
                or len(names) != len(set(names))
                or sum(f.file_size for f in files) > MAX_EXPANDED
                or any(f.flag_bits & 1 for f in files)
                or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", n) for n in names)
            ):
                raise EvidenceError("ZIP文件名、数量、加密或解压大小不符合报告协议")
            if "manifest.json" not in names:
                raise EvidenceError("缺少manifest.json，无法判断报告是否完整")
            manifest = json.loads(archive.read("manifest.json"))
            expected = manifest.get("expected_reports")
            if (
                manifest.get("version") != 1
                or not isinstance(expected, list)
                or not 1 <= len(expected) <= 20
                or any(
                    not isinstance(n, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]+\.xml", n)
                    for n in expected
                )
                or len(set(expected)) != len(expected)
                or set(names) - {"manifest.json", *expected}
            ):
                raise EvidenceError("manifest报告清单无效或包含额外文件")
            counts = dict(passed=0, failed=0, errors=0, skipped=0)
            reports = []
            for name in expected:
                if name not in names:
                    continue
                parsed = parse_junit(archive.read(name))
                reports.append({"name": name, **parsed})
                for key in counts:
                    counts[key] += parsed[key]
            return {
                **counts,
                "reports": reports,
                "complete": len(reports) == len(expected),
                "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
            }
    except EvidenceError:
        raise
    except (
        zipfile.BadZipFile,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        NotImplementedError,
        RuntimeError,
        OSError,
    ):
        raise EvidenceError("ZIP/JUnit报告不可解析") from None
