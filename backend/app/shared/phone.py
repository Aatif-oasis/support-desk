"""
Phone number validation shared by every endpoint that accepts one.

Kept here rather than duplicated per-schema so the widget, the agent
profile editor and the CRM API can never drift apart on what counts as a
valid number — a customer who reaches an agent with an unreachable phone
number is worse than one who was told to fix it at the form.

Deliberately permissive about formatting (people paste numbers with
spaces, dashes, brackets and country codes) and strict about content: the
digits are what a human will eventually dial.
"""
import re

# Letters anywhere is the giveaway for junk input, so they are rejected
# outright rather than stripped — "asdfgh1234567" should fail, not quietly
# become "1234567".
_ALLOWED_CHARS = re.compile(r"^[0-9+()\-.\s]+$")
_DIGITS = re.compile(r"\d")

MIN_DIGITS = 7   # shortest real national numbers
MAX_DIGITS = 15  # E.164 upper bound

# National length for the countries the widget offers, keyed by dial code.
# The widget checks this too, but the widget is JavaScript on someone
# else's page — anyone can edit it, so the rule has to hold here as well.
#
# Nine for Australia rather than a flat ten: an Australian mobile really
# is nine digits, and demanding ten would lock out every visitor there.
_NATIONAL_DIGITS_BY_DIAL = {
    "44": 10,   # United Kingdom
    "1": 10,    # United States and Canada
    "61": 9,    # Australia
    "91": 10,   # India
}


def normalize_phone(value: str) -> str:
    """
    Returns the number in a consistent form, or raises ValueError with a
    message written for the person filling in the form, not for a log file.
    """
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Enter a phone number.")

    if not _ALLOWED_CHARS.match(raw):
        raise ValueError("A phone number can only contain digits, spaces, and + - ( ) .")

    digits = "".join(_DIGITS.findall(raw))

    if len(digits) < MIN_DIGITS:
        raise ValueError("That phone number is too short to be real.")
    if len(digits) > MAX_DIGITS:
        raise ValueError("That phone number is too long to be real.")

    # A number that is one digit over and over (0000000000, 1111111111) is
    # the other common way people get past a length check.
    if len(set(digits)) == 1:
        raise ValueError("Enter a real phone number.")

    plus = "+" if raw.lstrip().startswith("+") else ""

    # Longest dial code first, so "1" doesn't shadow "91".
    if plus:
        for dial in sorted(_NATIONAL_DIGITS_BY_DIAL, key=len, reverse=True):
            if digits.startswith(dial):
                expected = _NATIONAL_DIGITS_BY_DIAL[dial]
                national = digits[len(dial):]
                if len(national) != expected:
                    raise ValueError(
                        f"A +{dial} number needs {expected} digits after the country code."
                    )
                break

    return f"{plus}{digits}"
