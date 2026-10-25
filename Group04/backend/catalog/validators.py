import pycountry
from django.core.exceptions import ValidationError


def validate_country_code(value):
    if value and pycountry.countries.get(alpha_2=value) is None:
        raise ValidationError("Enter a valid ISO 3166-1 two-letter country code.")


def validate_currency_code(value):
    if value and pycountry.currencies.get(alpha_3=value) is None:
        raise ValidationError("Enter a valid ISO 4217 currency code.")
