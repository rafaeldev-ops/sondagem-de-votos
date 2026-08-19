from starlette.requests import Request

from app.core.config import get_settings


def extrair_ip_do_cliente(request: Request) -> str | None:
    """
    IP de origem da requisição, para audit log e para a chave do rate limit.

    X-Forwarded-For só é confiado quando TRUST_PROXY_HEADERS=true está
    explicitamente configurado — ou seja, quando se sabe que a aplicação roda
    atrás de um proxy reverso confiável (nginx, Traefik, Cloudflare, load
    balancer de cloud) que SOBRESCREVE esse header nas requisições que
    encaminha. Sem essa garantia, qualquer cliente pode mandar o header à
    mão e escolher o IP que quiser — o que falsificaria o audit log e, pior,
    daria a qualquer um uma chave de rate limit nova a cada requisição,
    tornando o limite inútil.

    Mora aqui, e não em app/api/deps.py, porque tem DOIS consumidores com
    formatos incompatíveis: uma dependência async do FastAPI (o audit log) e
    a key_func síncrona do slowapi. Enquanto essa lógica existia só no
    deps.py, o limitador usava o get_remote_address do slowapi — que lê
    exclusivamente request.client.host e ignora X-Forwarded-For. Atrás de
    proxy, portanto, TODA requisição compartilhava a chave do IP do proxy, e
    os limites por pessoa viravam limites globais do site inteiro (10
    cadastros por minuto para todos os associados somados). O docstring do
    deps.py já dizia "para audit log e rate limiting", mas só a primeira
    metade era verdade.
    """
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # O primeiro da lista é o cliente original; os seguintes são os
            # proxies pelos quais passou.
            return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
