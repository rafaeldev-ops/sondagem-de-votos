import re


def normalize_cpf(cpf: str) -> str:
    return re.sub(r"\D", "", cpf)


def validate_cpf(cpf: str) -> bool:
    """Valida CPF usando algoritmo oficial dos dígitos verificadores."""
    cpf_digits = normalize_cpf(cpf)

    if len(cpf_digits) != 11:
        return False

    if cpf_digits == cpf_digits[0] * 11:
        return False

    def calc_digit(digits: str, weights: range) -> int:
        total = sum(int(d) * w for d, w in zip(digits, weights, strict=True))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    first = calc_digit(cpf_digits[:9], range(10, 1, -1))
    if first != int(cpf_digits[9]):
        return False

    second = calc_digit(cpf_digits[:10], range(11, 1, -1))
    return second == int(cpf_digits[10])


def format_cpf(cpf: str) -> str:
    digits = normalize_cpf(cpf)
    if len(digits) != 11:
        return cpf
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


def mask_cpf(cpf: str) -> str:
    """Mascara para uso em logs/exibição: nunca gravar o CPF completo em
    texto puro em nenhum log de aplicação (LGPD)."""
    digits = normalize_cpf(cpf)
    if len(digits) != 11:
        return "***.***.***-**"
    return f"***.***.**{digits[8]}-{digits[9:]}"
