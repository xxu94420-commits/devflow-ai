import io
import json
import zipfile

import pytest

from app.junit import EvidenceError, parse_bundle, parse_junit


def bundle(files=None, expected=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"version": 1, "expected_reports": expected or ["backend.xml"]}),
        )
        for name, data in (files or {}).items():
            archive.writestr(name, data)
    return output.getvalue()


XML = b"""<testsuites tests="999"><testsuite tests="999">
<testcase name="pass"/><testcase name="fail"><failure>SECRET</failure></testcase>
<testcase name="error"><error/></testcase><testcase name="skip"><skipped/></testcase>
</testsuite></testsuites>"""


def test_counts_leaf_cases_not_untrusted_parent_totals():
    counts = parse_junit(XML)
    assert counts == dict(passed=1, failed=1, errors=1, skipped=1)
    result = parse_bundle(bundle({"backend.xml": XML}))
    assert result["complete"] and result["passed"] == 1
    assert "SECRET" not in str(result)
    assert result["digest"].startswith("sha256:")


def test_partial_and_all_skipped_are_not_successful_executions():
    partial = parse_bundle(
        bundle({"backend.xml": XML}, ["backend.xml", "frontend.xml"])
    )
    assert not partial["complete"]
    assert partial["failed"] == 1
    assert (
        parse_junit(b"<testsuite><testcase><skipped/></testcase></testsuite>")["passed"]
        == 0
    )


@pytest.mark.parametrize(
    "xml",
    [
        b'<!DOCTYPE t [<!ENTITY x "boom">]>'
        b"<testsuite><testcase>&x;</testcase></testsuite>",
        b'<testsuite tests="8"/>',
        b"<invalid/>",
        b"<testsuite>",
    ],
)
def test_unverifiable_or_unsafe_xml_rejected(xml):
    with pytest.raises(EvidenceError):
        parse_junit(xml)


@pytest.mark.parametrize(
    "files",
    [
        {"../backend.xml": XML},
        {"backend.xml": XML, "secret.txt": b"secret"},
        {"backend.xml": b"a" * (9 * 1024 * 1024)},
    ],
)
def test_zip_traversal_unknown_files_and_compression_bombs_rejected(files):
    with pytest.raises(EvidenceError):
        parse_bundle(bundle(files))


def test_missing_manifest_and_duplicate_zip_names_rejected():
    with pytest.raises(EvidenceError):
        parse_bundle(b"not a zip")
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("backend.xml", XML)
    with pytest.raises(EvidenceError):
        parse_bundle(data.getvalue())
