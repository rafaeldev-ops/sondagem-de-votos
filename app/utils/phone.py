import re


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("55") and len(digits) > 11:
        digits = digits[2:]
    return digits


def validate_phone(phone: str) -> bool:
    digits = normalize_phone(phone)
    if len(digits) not in (10, 11):
        return False
    if len(digits) == 11:
        return digits[2] == "9"
    return True


def format_phone(phone: str) -> str:
    digits = normalize_phone(phone)
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return phone
