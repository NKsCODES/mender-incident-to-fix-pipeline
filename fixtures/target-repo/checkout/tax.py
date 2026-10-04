REGION_RATES = {"MH": 0.18, "KA": 0.18, "DL": 0.18, "EXPORT": 0.0}


def tax_cents(subtotal_cents: int, region: str | None) -> int:
    """GST for a region code. A missing region (None) is an export order, zero rated."""
    return round(subtotal_cents * REGION_RATES[region.upper()])
