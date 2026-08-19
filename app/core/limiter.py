from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.utils.client_ip import extrair_ip_do_cliente


def chave_do_limitador(request: Request) -> str:
    """
    Chave de contagem do rate limit: o IP real do cliente.

    NÃO usar o get_remote_address do slowapi direto como key_func. Ele lê
    apenas request.client.host e ignora X-Forwarded-For — atrás de um proxy
    reverso, todas as requisições passam a contar na mesma chave (a do
    proxy), e cada limite "por IP" vira um limite global do site: com
    RATE_LIMIT_REGISTER=30/minute, seriam 30 cadastros por minuto somando
    TODOS os associados, e o resto receberia 429.

    extrair_ip_do_cliente só confia em X-Forwarded-For quando
    TRUST_PROXY_HEADERS=true, então a versão sem proxy continua imune a
    header forjado — ver o docstring lá para o raciocínio completo.

    O get_remote_address fica como último recurso porque a key_func precisa
    devolver str, nunca None: sem client e sem header confiável (acontece em
    transporte ASGI de teste), ele devolve o fallback "127.0.0.1" em vez de
    quebrar a requisição.
    """
    return extrair_ip_do_cliente(request) or get_remote_address(request)


limiter = Limiter(key_func=chave_do_limitador)
