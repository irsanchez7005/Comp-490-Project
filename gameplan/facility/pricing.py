"""Receipt calculations for tee time bookings."""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

TAX_RATE = Decimal("0.095")
NO_DISCOUNT = Decimal("0.00")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Receipt:
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal


def _round_to_cents(amount):
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_receipt(price_per_player, players):
    """Return the amounts owed for a number of players at a per-player price."""
    subtotal = _round_to_cents(price_per_player * players)
    tax = _round_to_cents((subtotal - NO_DISCOUNT) * TAX_RATE)
    return Receipt(
        subtotal=subtotal,
        discount=NO_DISCOUNT,
        tax=tax,
        total=subtotal - NO_DISCOUNT + tax,
    )
