"""check_connection: prove the robot can log on and that the session is the expected one.

The worker has already logged on (or reused a leftover robot session), compared system, client
and user, and run the T-code guard. This step only reports who is logged on; it sends no T-code
and presses nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime

from shoponline.saprobot.worker import JobContext, TransactionResult


def run(ctx: JobContext) -> TransactionResult:
    who = ctx.identity
    return TransactionResult(
        data={
            "system": who.system,
            "client": who.client,
            "user": who.user,
            "logged_on_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "gui_version": ctx.gui_version,
        }
    )
