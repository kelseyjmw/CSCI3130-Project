import string

from django.core.exceptions import ValidationError

import re
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone


class PasswordRequirementsValidator:
    def validate(self, password, user=None):
        errors = []
        if len(password) < 6:
            errors.append('Password must be at least 6 characters long.')
        if not any(character in string.digits for character in password):
            errors.append('Password must contain at least one digit (0-9).')
        if not any(character in string.punctuation for character in password):
            errors.append('Password must contain at least one special character (e.g., @, #, !).')
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return 'Use at least 6 characters, including a digit (0-9) and a special character (e.g., @, #, !).'


def validate_top_up_card(amount, card_number, cvv, expiry):
    """
    Validates card top-up input according to Release 6 requirements:
    - Amount: positive decimal with at most two decimal places.
    - Card number: exactly 16 digits.
    - CVV: exactly 3 digits (including leading zeros, e.g., '007').
    - Expiry: MM/YYYY or MM/YY strictly after the current server month.
      In November 2026, 11/2026 fails and 12/2026 passes.
    """
    errors = {}

    # 1. Amount validation
    try:
        dec_amount = Decimal(str(amount))
        if dec_amount <= Decimal('0.00'):
            errors['amount'] = "Amount must be positive."
        elif dec_amount.as_tuple().exponent < -2:
            errors['amount'] = "Amount cannot have more than two decimal places."
    except Exception:
        errors['amount'] = "Enter a valid positive amount."

    # 2. Card number validation (exactly 16 digits)
    card_str = str(card_number).strip().replace(" ", "").replace("-", "")
    if not re.fullmatch(r'^\d{16}$', card_str):
        errors['card_number'] = "Card number must be exactly 16 digits."

    # 3. CVV validation (exactly 3 digits, preserving leading zeroes)
    cvv_str = str(cvv).strip()
    if not re.fullmatch(r'^\d{3}$', cvv_str):
        errors['cvv'] = "CVV must be exactly three digits."

    # 4. Expiry validation (MM/YYYY strictly after current server month)
    expiry_match = re.fullmatch(r'^(\d{1,2})/(\d{2}|\d{4})$', str(expiry).strip())
    if not expiry_match:
        errors['expiry'] = "Expiry must be in MM/YYYY format."
    else:
        exp_month = int(expiry_match.group(1))
        exp_year = int(expiry_match.group(2))
        if exp_year < 100:
            exp_year += 2000

        if not (1 <= exp_month <= 12):
            errors['expiry'] = "Expiry month must be between 01 and 12."
        else:
            now = timezone.now()
            current_year = now.year
            current_month = now.month
            
            # Must be strictly after current month
            if (exp_year < current_year) or (exp_year == current_year and exp_month <= current_month):
                errors['expiry'] = "Card expiry date must be strictly after the current month."

    if errors:
        raise ValidationError(errors)

    return dec_amount