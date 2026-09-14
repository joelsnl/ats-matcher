"""Repeatable fictional cases for comparing local models/prompts. No real CVs.

Example: python scripts/evaluate_coaching.py --url http://127.0.0.1:8879
The report records outputs and latency, not an automatic claim of writing quality.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


PROFILE = {
    "name": "Taylor Example", "skills": ["Python", "Jenkins"],
    "recent_titles": ["Software Engineer"],
    "employers": [{"name": "Example Agency", "client": "Example Client"}],
    "achievements": "On assignment from Example Agency at Example Client, I wrote Python checks for imported files. "
                    "I checked required fields and logged invalid rows. I explained the error report to stakeholders. "
                    "I maintained Jenkins build steps. No measured outcome was recorded.",
    "motivation": "I enjoy work that combines validation tools with explaining decisions to a team.",
}
JOB = {"title": "Platform Engineer", "company": "Fictional Studio",
       "description": "Required: Python, CI/CD and Kubernetes. Explain technical decisions to stakeholders. "
                      "Nice to have: Terraform. The role involves validation tooling and deployment support."}
CASES = ("letter-en", "letter-nl", "revision", "foundation", "refresher", "people-skill")


def call(base: str, route: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(base + route, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=330) as response:
            return json.load(response)
    except HTTPError as error:
        result = json.loads(error.read())
        raise RuntimeError(result.get("error", f"HTTP {error.code}")) from None


def run_case(base: str, case: str) -> dict:
    payload = {"profile": PROFILE, "job": JOB}
    if case.startswith("letter-"):
        return call(base, "/api/cover-letter", {**payload, "options": {
            "language": case.split("-")[1], "length": "concise", "tone": "direct"}})
    if case == "revision":
        selected = "I wrote Python checks for imported files, checking required fields and logging invalid rows."
        letter = "Dear Fictional Studio team,\n\n" + selected + "\n\n" + (
            "Your Platform Engineer role interests me because it combines validation tools with deployment support. "
            "On assignment from Example Agency at Example Client, I maintained Jenkins build steps and explained "
            "error reports to stakeholders. I would welcome a discussion about this work and your team's priorities."
        ) + "\n\nTaylor Example"
        start = letter.index(selected)
        return call(base, "/api/cover-letter-revise", {**payload, "letter": letter,
                    "start": start, "end": start + len(selected), "instruction": "plain"})
    context = call(base, "/api/role-analysis", payload)
    name = {"foundation": "Kubernetes", "refresher": "Python", "people-skill": "Communication"}[case]
    requirement = next(row for row in context["requirements"] if row["name"] == name)
    return call(base, "/api/practice-lesson", {**payload, "skill_id": requirement["id"],
        "mode": "rehearsal" if case == "people-skill" else case, "tailor": True,
        "focus": "I want to explain the failure case, not just the successful path."})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8879")
    parser.add_argument("--case", choices=("all", *CASES), default="all")
    parser.add_argument("--label", default="local-model", help="Model/prompt label for comparing reports")
    parser.add_argument("--output", type=Path, default=Path(".cache/coaching-evaluation.json"))
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password:
        parser.error("Use the loopback HTTP address of your local app.")
    base = args.url.rstrip("/")
    report = {"label": args.label, "created_at": datetime.now(timezone.utc).isoformat(),
              "health": call(base, "/api/health"), "profile": PROFILE, "job": JOB, "cases": [],
              "human_review": ["Are every employer, tool claim, outcome and number supported?",
                               "Is the requested language natural and the wording specific to the role?",
                               "Can the learner attempt the exercise using its supplied information?",
                               "Does the difficulty match foundations, refreshers, or people-skill practice?",
                               "Is the waiting time acceptable for this interaction?"],
              "note": "Automated claim checks are incomplete. Review the saved outputs before ranking models."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    failures = 0
    for case in CASES if args.case == "all" else (args.case,):
        print(f"Running {case}…", flush=True)
        started = time.monotonic()
        try:
            result = {"case": case, "output": run_case(base, case)}
        except Exception as error:
            result = {"case": case, "error": str(error)}
            failures += 1
        result["seconds"] = round(time.monotonic() - started, 2)
        report["cases"].append(result)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved {case}: {result['seconds']} seconds", flush=True)
    print(f"Report: {args.output}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
