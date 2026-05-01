"""
Daily auto-run scheduler — V1 E5.

Per-user daily trigger that runs `_start_agent_thread("full", ...)` at the
HH:MM (IST) chosen in profile.auto_run_time, but only when
profile.auto_run_enabled is True.

Implementation notes:
- Pure-stdlib (no APScheduler dep). One background thread polls every 30s,
  reads all profiles, and fires whatever matches.
- Tracks last-fired DATE (not minute) per user in memory so a single 1-minute
  window doesn't re-trigger after the first hit.
- Defers to `_start_agent_thread`, which already enforces the global browser
  semaphore — if a manual run is in progress, scheduled runs back off.
- Default platforms = ["linkedin", "naukri", "ats"] (V1 live sources). Can be
  overridden by setting profile.scheduled_platforms (currently unused).
"""
from __future__ import annotations
import logging
import threading
import time
from datetime import datetime, timezone, timedelta, date

from db.database import SessionLocal
from db.models import Profile

logger = logging.getLogger("scheduler")

IST = timezone(timedelta(hours=5, minutes=30))

# Default sources for scheduled runs. Internshala/Unstop are excluded from
# auto-run for V1 — they're discovery-only and not part of the V1 launch DoD.
DEFAULT_PLATFORMS = ["linkedin", "naukri", "ats"]

POLL_INTERVAL_SEC = 30


class DailyScheduler:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        # user_id → date object representing the last day we fired for that user
        self._last_run: dict[int, date] = {}

    # ── Public lifecycle ────────────────────────────────────────────────

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="daily-scheduler"
        )
        self._thread.start()
        logger.info("[scheduler] started")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[scheduler] stopped")

    # ── Inner loop ──────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                logger.exception(f"[scheduler] tick crashed: {e}")
            # Sleep with early-wake on stop
            self._stop.wait(POLL_INTERVAL_SEC)

    def _tick(self):
        now_ist = datetime.now(IST)
        hhmm = now_ist.strftime("%H:%M")
        today = now_ist.date()

        db = SessionLocal()
        try:
            rows = db.query(Profile).filter(Profile.auto_run_enabled.is_(True)).all()
            for p in rows:
                if not p.user_id:
                    continue
                target = (p.auto_run_time or "09:00").strip()[:5]
                if target != hhmm:
                    continue
                if self._last_run.get(p.user_id) == today:
                    continue  # already fired today

                self._fire(p.user_id)
                self._last_run[p.user_id] = today
        finally:
            db.close()

    def _fire(self, user_id: int):
        # Lazy import to avoid a circular dep with api.agent
        from api.agent import _start_agent_thread, _get_user_state, _log

        st = _get_user_state(user_id)
        if st.get("running"):
            logger.info(f"[scheduler] u{user_id}: agent already running, skipping")
            return

        _log(f"⏰ Daily auto-run triggered ({datetime.now(IST).strftime('%H:%M IST')})", user_id)
        t, err = _start_agent_thread("full", DEFAULT_PLATFORMS, user_id)
        if err:
            logger.warning(f"[scheduler] u{user_id}: dispatch failed: {err}")
            _log(f"⚠️ Auto-run dispatch failed: {err}", user_id)
            return
        logger.info(f"[scheduler] u{user_id}: dispatched full agent run")


# Module-level singleton.
scheduler = DailyScheduler()
