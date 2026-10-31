"""Escalation worker: sends due steps, expires unacknowledged ones and records unanswered alarms.

    python -m app.escalation_worker            # loop (every 2 s)
    python -m app.escalation_worker --once     # one pass, then exit (cron or tests)

Uses the same settings as the API (PULSE_DATABASE_URL). It does nothing unless PULSE_ESCALATION_ENABLED is on,
because no episode is made eligible otherwise. Several workers may run at once (FOR UPDATE SKIP LOCKED).
If the worker stops, the patient's emergency screen still works: it never depends on this process.
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone

from .config import load_settings
from .db import make_engine, make_session_factory
from .services import escalation

INTERVAL_S = 2.0
log = logging.getLogger("pulse.escalation")


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    settings = load_settings()
    if not settings.database_url:
        log.error("PULSE_DATABASE_URL is not set")
        return 2
    if not settings.escalation_enabled:
        log.warning("PULSE_ESCALATION_ENABLED is off: no episode is eligible, the worker has nothing to send")
    sessions = make_session_factory(make_engine(settings.database_url))
    once = "--once" in argv
    while True:
        started = time.monotonic()
        try:
            with sessions() as db:
                changed = escalation.run_once(db, datetime.now(timezone.utc))
            if changed:
                log.info("pass: %d change(s)", changed)
        except Exception:  # keep running: one bad pass must not stop the escalations of other patients
            log.exception("pass failed")
            if once:
                return 1
        if once:
            return 0
        time.sleep(max(0.0, INTERVAL_S - (time.monotonic() - started)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
