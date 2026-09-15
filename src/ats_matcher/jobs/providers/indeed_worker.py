"""One-shot JobSpy worker; native library failures cannot terminate the app."""
from __future__ import annotations

import contextlib
import json
import sys


def main():
    kwargs = json.load(sys.stdin)
    # Third-party diagnostic output must not corrupt the JSON response.
    with contextlib.redirect_stdout(sys.stderr):
        from jobspy import scrape_jobs

        frame = scrape_jobs(**kwargs)
        payload = "[]" if frame is None else frame.to_json(orient="records", date_format="iso")
    sys.stdout.write(payload)


if __name__ == "__main__":
    main()
