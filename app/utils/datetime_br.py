from datetime import datetime
from zoneinfo import ZoneInfo

_FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")


def format_datetime_br(dt: datetime) -> str:
    """
    "19/08/2026 14:32 (BRT)" em vez do ISO 8601 cru que o banco devolve
    (timestamptz vem em UTC). Convertido para o horário de Brasília antes
    de formatar — é o fuso de quem lê a planilha.
    """
    local = dt.astimezone(_FUSO_BRASILIA)
    return f"{local.strftime('%d/%m/%Y %H:%M')} (BRT)"
