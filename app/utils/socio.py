import re

# Exatamente 4 dígitos ASCII. Deliberadamente [0-9] e não \d nem
# str.isdigit(): os dois últimos aceitam dígitos unicode ("٤".isdigit() e
# "²".isdigit() são ambos True), o que deixaria entrar no banco um "número
# de sócio" que não corresponde a nenhum número real do quadro social.
_NUMERO_SOCIO_RE = re.compile(r"[0-9]{4}")


def normalize_numero_socio(valor: str) -> str:
    return re.sub(r"\D", "", valor)


def validate_numero_socio(valor: str) -> bool:
    return _NUMERO_SOCIO_RE.fullmatch(valor) is not None
