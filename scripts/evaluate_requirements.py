"""Opt-in live evaluation on public synthetic inputs; never invent model scores."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import get_settings  # noqa: E402
from app.review_contract import PROMPT_VERSION, fingerprint  # noqa: E402
from app.review_provider import ReviewFailure, connection, generate  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--provider", choices=["cloud", "ollama"], default="cloud")
parser.add_argument("--allow-model-call", action="store_true")
parser.add_argument("--output", default="reports/requirement-eval.json")
args = parser.parse_args()
dataset = json.loads(
    (ROOT / "backend/evals/requirement-cases.json").read_text(encoding="utf-8")
)
if not args.allow_model_call:
    print(
        f"Dataset valid: {len(dataset['cases'])} synthetic cases; no model calls or quality scores generated."
    )
    raise SystemExit(0)

# Resolve .env independently of invocation directory, without printing secrets.
get_settings.cache_clear()
from app.config import Settings  # noqa: E402

settings = Settings(_env_file=ROOT / ".env")
import app.review_provider as provider_module  # noqa: E402

provider_module.get_settings = lambda: settings
try:
    config = connection(args.provider)
except (ReviewFailure, ValueError):
    raise SystemExit("No configured connection; live evaluation not run") from None
results = []
for case in dataset["cases"]:
    source = {k: case[k] for k in ("title", "description", "acceptance_criteria")} | {
        "version": 1
    }
    result = {
        "id": case["id"],
        "input_hash": fingerprint(source),
        "expected_categories": case["expected_categories"],
    }
    try:
        findings, usage = generate(source, config)
        observed = sorted({f["category"] for f in findings})
        result.update(
            status="succeeded",
            findings=findings,
            usage=usage,
            observed_categories=observed,
            missed_categories=sorted(set(case["expected_categories"]) - set(observed)),
            extra_categories=sorted(set(observed) - set(case["expected_categories"])),
        )
    except ReviewFailure as exc:
        result.update(status="failed", error_code=exc.code)
    results.append(result)
output = {
    "label": dataset["label"],
    "dataset_version": dataset["version"],
    "prompt_version": PROMPT_VERSION,
    "model": config["model"],
    "provider": config["url"],
    "at": datetime.now(timezone.utc).isoformat(),
    "note": "Category differences are review candidates, not calibrated accuracy or efficiency claims.",
    "results": results,
}
path = ROOT / args.output
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
print(
    f"Saved {len(results)} actual attempt records to {path}; inspect failures and false alarms manually."
)
