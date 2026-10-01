"""Local maintainer helper: reuse Git credential helper, never print credentials."""

import argparse
import json
import subprocess

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("method", choices=["GET", "POST", "PATCH"])
parser.add_argument("path", help="Path relative to this project's repository API")
parser.add_argument("--body-file")
args = parser.parse_args()
credential = subprocess.run(
    ["git", "credential", "fill"],
    input="protocol=https\nhost=github.com\n\n",
    text=True, capture_output=True, check=True,
)
fields = dict(line.split("=", 1) for line in credential.stdout.splitlines() if "=" in line)
body = None
if args.body_file:
    with open(args.body_file, encoding="utf-8") as source:
        body = json.load(source)
with httpx.Client(timeout=30) as client:
    response = client.request(
        args.method,
        "https://api.github.com/repos/xxu94420-commits/devflow-ai"
        + ("" if args.path == "." else "/" + args.path.lstrip("/")),
        headers={"Authorization": "Bearer " + fields["password"],
                 "Accept": "application/vnd.github+json"},
        json=body,
    )
if response.is_error:
    print(f"GitHub API status {response.status_code}; no credentials logged")
    raise SystemExit(1)
result = response.json()
if isinstance(result, dict) and "workflow_runs" in result:
    print(json.dumps([{k: x.get(k) for k in (
        "id", "head_sha", "status", "conclusion", "html_url", "head_branch"
    )} for x in result["workflow_runs"]]))
    raise SystemExit(0)
if isinstance(result, dict) and "jobs" in result:
    print(json.dumps([{k: x.get(k) for k in (
        "id", "name", "status", "conclusion", "steps"
    )} for x in result["jobs"]]))
    raise SystemExit(0)
if isinstance(result, list):
    print(json.dumps([{k: x.get(k) for k in ("number", "title", "html_url", "state")} for x in result]))
else:
    print(json.dumps({k: result.get(k) for k in ("number", "title", "html_url", "state", "sha")}))
