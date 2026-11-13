"""Put the SAP settings row of a test database in a known state."""

from __future__ import annotations

from sqlalchemy.orm import Session

from shoponline.sapjobs import sap_settings
from shoponline.sapjobs.queue import SapTarget

NO_ENV: dict[str, str] = {}  # tests never read the developer's real SHOPONLINE_SAP_* variables


def configure_sap(
    db: Session,
    target: SapTarget | None,
    *,
    verified: bool = True,
    user: str = "robot01",
    connection: str = "QA robot",
    **fields,
) -> None:
    """Store target (or an empty target) and, when asked, mark it as checked."""
    sap_settings.save(
        db,
        "test",
        NO_ENV,
        system=target.system if target else "",
        client=target.client if target else "",
        connection=connection,
        sap_user=user,
        **fields,
    )
    if target is not None and verified:
        sap_settings.mark_verified(db, NO_ENV, target.system, target.client)
    db.flush()
