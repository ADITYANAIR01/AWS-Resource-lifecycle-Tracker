"""
AWS Resource Lifecycle Tracker — Poller
Phase 0: Skeleton — DB connection verified, poll loop running.
No collectors loaded yet. Added in Phase 3 onwards.
"""

import os
import signal
import sys
import time

from db.connection import close_pool, init_pool
from utils.logger import get_logger

logger = get_logger("poller.main")

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info(f"Received signal {signum} — shutting down gracefully")
    _shutdown = True


def get_poll_interval() -> int:
    minutes = int(os.environ.get("POLL_INTERVAL_MINUTES", 60))
    return minutes * 60


def run_poll_cycle() -> None:
    logger.info("Poll cycle started")
    # Phase 3: collectors called here
    # Phase 5: alert evaluator called here
    # Phase 8: static export generator called here
    logger.info("Poll cycle complete — no collectors loaded yet (Phase 0)")


def main() -> None:
    logger.info("=" * 60)
    logger.info("AWS Resource Lifecycle Tracker — Poller starting")
    logger.info("=" * 60)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        init_pool()
    except Exception as e:
        logger.error(f"Fatal: could not initialise DB pool: {e}")
        sys.exit(1)

    logger.info(
        f"Poller ready — poll interval: "
        f"{os.environ.get('POLL_INTERVAL_MINUTES', 60)} minutes"
    )
    logger.info("No collectors loaded yet — this is Phase 0")

    poll_interval = get_poll_interval()

    while not _shutdown:
        try:
            run_poll_cycle()
        except Exception as e:
            logger.error(f"Unexpected error in poll cycle: {e}", exc_info=True)

        logger.info(f"Sleeping {poll_interval // 60} minutes until next poll")

        for _ in range(poll_interval):
            if _shutdown:
                break
            time.sleep(1)

    logger.info("Poller shutting down")
    close_pool()
    logger.info("Poller stopped cleanly")


if __name__ == "__main__":
    main()