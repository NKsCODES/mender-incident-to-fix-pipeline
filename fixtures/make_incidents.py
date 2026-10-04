"""Trigger each latent bug in target-repo and capture the real traceback as a
Sentry-style event. Run after any change to target-repo so line numbers match."""
import json
import linecache
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE / "target-repo"
sys.path.insert(0, str(REPO))
from checkout import handlers  # noqa: E402

CASES = {
    "pricing-zero-qty": (handlers.line_summary, {"total_cents": 0, "qty": 0}, "POST /cart/lines/summary", 212),
    "currency-lowercase": (handlers.quote, {"amount_cents": 100, "from": "usd", "to": "inr"}, "POST /quote", 87),
    "inventory-unknown-sku": (handlers.reserve, {"stock": {"A": 1}, "sku": "ZZ-9", "qty": 1}, "POST /reserve", 41),
    "cart-empty": (handlers.cart_view, {"items": []}, "GET /cart", 530),
    "tax-missing-region": (handlers.invoice, {"subtotal_cents": 1000}, "POST /invoice", 64),
    "coupon-percent-sign": (handlers.apply_coupon, {"value": "10%"}, "POST /coupon", 118),
    "shipping-drone": (handlers.delivery, {"distance_km": 12, "mode": "drone"}, "GET /delivery/eta", 9),
}

for event_id, (fn, payload, route, count) in CASES.items():
    try:
        fn(payload)
    except Exception as exc:  # noqa: BLE001 - capturing is the point
        frames = []
        for f in traceback.extract_tb(exc.__traceback__):
            p = Path(f.filename)
            if REPO not in p.parents:
                continue
            frames.append({
                "filename": str(p.relative_to(REPO)),
                "lineno": f.lineno,
                "function": f.name,
                "context_line": linecache.getline(f.filename, f.lineno).strip(),
                "in_app": True,
            })
        event = {
            "event_id": event_id,
            "service": "checkout",
            "environment": "production",
            "release": "checkout@2026.10.1",
            "exception": {"type": type(exc).__name__, "value": str(exc), "frames": frames},
            "request": {"route": route, "payload": payload},
            "count": count,
        }
        (HERE / "incidents" / f"{event_id}.json").write_text(json.dumps(event, indent=2) + "\n")
        print(event_id, type(exc).__name__, frames[-1]["filename"], frames[-1]["lineno"])
    else:
        raise SystemExit(f"{event_id} did not fail")
