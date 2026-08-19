import contextvars
import json
import logging
import sys
from datetime import UTC, datetime

# Request ID da requisição em curso, propagado automaticamente para todo log
# emitido durante o processamento dela (ver RequestIdMiddleware). Usar
# ContextVar em vez de passar o id explicitamente mantém as assinaturas de
# service/repository intocadas.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Formata cada log como uma linha JSON — formato esperado por
    agregadores (CloudWatch, Loki, Datadog etc). Um log legível a olho nu
    é ótimo em desenvolvimento e péssimo para busca/alerta em produção."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(json_logs: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())

    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | [%(request_id)s] | %(message)s"
            )
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
