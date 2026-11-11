"""Platform product/variation name -> SAP material, one table per platform."""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import SkuMapping
from shoponline.domain.states import log_event

_SPACES = re.compile(r"\s+")


def normalize_key(text: str) -> str:
    """NFC, collapse runs of whitespace, trim. Case and punctuation are kept as is."""
    return _SPACES.sub(" ", unicodedata.normalize("NFC", text or "")).strip()


def find_mapping(
    session: Session, platform: str, product_name: str, variation_name: str
) -> SkuMapping | None:
    return session.scalar(
        select(SkuMapping).where(
            SkuMapping.platform == platform,
            SkuMapping.product_key == normalize_key(product_name),
            SkuMapping.variation_key == normalize_key(variation_name),
        )
    )


def validate_material_number(material_number: str) -> str:
    value = (material_number or "").strip()
    if not value.isdigit():
        raise ValueError(f"Mã SAP phải là chữ số: {material_number!r}")
    return value


def upsert_mapping(
    session: Session,
    platform: str,
    product_name: str,
    variation_name: str,
    material_number: str,
    sap_name: str,
    actor: str,
) -> tuple[SkuMapping, bool]:
    """Create or update one mapping. Returns (mapping, changed)."""
    material = validate_material_number(material_number)
    sap_name = (sap_name or "").strip()
    if not sap_name:
        raise ValueError("Tên SAP không được trống")
    if not normalize_key(product_name):
        raise ValueError("Tên sản phẩm không được trống")
    mapping = find_mapping(session, platform, product_name, variation_name)
    if mapping is None:
        mapping = SkuMapping(
            platform=platform,
            product_key=normalize_key(product_name),
            variation_key=normalize_key(variation_name),
            product_name=normalize_key(product_name),
            variation_name=normalize_key(variation_name),
            material_number=material,
            sap_name=sap_name,
            updated_by=actor,
        )
        session.add(mapping)
    elif mapping.material_number == material and mapping.sap_name == sap_name:
        return mapping, False
    else:
        mapping.material_number = material
        mapping.sap_name = sap_name
        mapping.updated_by = actor
    session.flush()
    log_event(
        session,
        actor,
        "sku_mapping_saved",
        platform=platform,
        detail={
            "product": mapping.product_name,
            "variation": mapping.variation_name,
            "material": material,
        },
    )
    return mapping, True
