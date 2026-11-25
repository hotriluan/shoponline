"""Management reporting: history of sales from 2022 and the views over it."""

from datetime import datetime

# Sales before this moment come from the accountants' history file, from it on from the system's
# own orders. The system's earliest order was placed at 2026-11-11 10:32, so no order is in both.
REPORTING_CUTOVER = datetime(2026, 11, 11)
