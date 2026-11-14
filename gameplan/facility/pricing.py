"""Receipt calculations for tee time bookings."""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

TAX_RATE = Decimal("0.095") # 9.5% tax rate
NO_DISCOUNT = Decimal("0.00") # No discount applied
CENT = Decimal("0.01") # Represents one cent for rounding purposes

""" Represents a receipt for a tee time booking. """
@dataclass(frozen=True) # Immutable data class
class Receipt:          # class to hold receipt details
    subtotal: Decimal   # The subtotal amount before tax and discounts for example, if the price per player is $50 and there are 4 players, the subtotal would be $200.
    discount: Decimal   # The discount amount applied to the subtotal, which is currently set to NO_DISCOUNT (0.00) in this implementation.
    tax: Decimal        # The tax amount calculated based on the subtotal and the TAX_RATE, which is 9.5% in this case. 
    total: Decimal      # The total amount including the subtotal, discount, and tax.

""" Rounds a Decimal amount to the nearest cent. """
def _round_to_cents(amount):
    return amount.quantize(CENT, rounding=ROUND_HALF_UP) # Rounds the amount to the nearest cent using the ROUND_HALF_UP method, which is a common rounding method where values exactly halfway between two possible rounded values are rounded up.


def calculate_receipt(price_per_player, players): #calculates the receipt for a tee time booking based on the price per player and the number of players.
    """Return the amounts owed for a number of players at a per-player price."""
    subtotal = _round_to_cents(price_per_player * players)     # Calculates the subtotal by multiplying the price per player by the number of players and rounding it to the nearest cent.
    tax = _round_to_cents((subtotal - NO_DISCOUNT) * TAX_RATE) # Calculates the tax by applying the TAX_RATE to the subtotal (after subtracting any discount, which is currently set to NO_DISCOUNT) and rounding it to the nearest cent. for example, if the subtotal is $200 and the tax rate is 9.5%, the tax would be $19.00.
    return Receipt(
        subtotal=subtotal, # The subtotal amount before tax and discounts.
        discount=NO_DISCOUNT,  # The discount amount applied to the subtotal, which is currently set to NO_DISCOUNT (0.00) in this implementation.
        tax=tax,                           # The tax amount calculated based on the subtotal and the TAX_RATE, which is 9.5% in this case.
        total=subtotal - NO_DISCOUNT + tax, # The total amount including the subtotal, discount, and tax. In this case, since the discount is set to NO_DISCOUNT (0.00), the total is simply the subtotal plus the tax.
    )
