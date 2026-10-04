"""Request handlers. Production incidents enter through these."""
from checkout import cart, coupon, currency, pricing, shipping, tax
from checkout.inventory import Inventory


def line_summary(payload: dict) -> dict:
    return {"unit_price": pricing.unit_price(payload["total_cents"], payload["qty"])}


def quote(payload: dict) -> dict:
    return {"amount": currency.convert(payload["amount_cents"], payload["from"], payload["to"])}


def reserve(payload: dict) -> dict:
    inv = Inventory(payload["stock"])
    return {"remaining": inv.reserve(payload["sku"], payload["qty"])}


def cart_view(payload: dict) -> dict:
    items = payload["items"]
    return {"currency": cart.cart_currency(items), "total": cart.cart_total(items)}


def invoice(payload: dict) -> dict:
    return {"tax": tax.tax_cents(payload["subtotal_cents"], payload.get("region"))}


def apply_coupon(payload: dict) -> dict:
    return {"percent": coupon.parse_percent(payload["value"])}


def delivery(payload: dict) -> dict:
    return {"eta_days": shipping.eta_days(payload["distance_km"], payload["mode"])}
