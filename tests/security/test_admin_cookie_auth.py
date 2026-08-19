"""
Sessão do admin em cookie httpOnly + proteção de CSRF.

Antes o JWT ficava em localStorage (static/js/admin.js), de onde um XSS o
lia com uma linha de script e podia reutilizá-lo fora do navegador da
vítima. Agora vive num cookie httpOnly, que o JS não alcança.

Trocar header por cookie abre a porta do CSRF — o navegador anexa cookie
sozinho, header Authorization não. Daí o double submit cookie validado em
validate_csrf() (app/api/deps.py), testado aqui.

Nota sobre logins: a rota de login tem rate limit de 5/minuto e a suíte
inteira roda do mesmo IP em poucos segundos. Por isso existe um único
login por sessão de testes (fixture `login_response`); os demais testes
montam os cookies à mão. Isso é possível porque o double submit é
stateless: o servidor compara o cookie com o header, sem guardar o valor
do CSRF em lugar nenhum.
"""

import httpx
import pytest
import pytest_asyncio

from app.core.security import ADMIN_CSRF_COOKIE, ADMIN_TOKEN_COOKIE


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def login_response(_live_server):
    """Um único login real por sessão — ver nota sobre rate limit acima."""
    base_url, _ = _live_server
    async with httpx.AsyncClient(base_url=base_url, timeout=10) as ac:
        res = await ac.post(
            "/api/admin/login", json={"username": "admin", "password": "admin123"}
        )
        assert res.status_code == 200, f"setup: login falhou: {res.status_code} {res.text}"
        return res


@pytest_asyncio.fixture
async def cliente_com_cookies(_live_server):
    """
    Fabrica clientes HTTP com os cookies já no cookie jar da instância.

    Passar cookies por requisição está deprecado no httpx (o comportamento
    de persistência é ambíguo), então cada cenário ganha um cliente
    próprio com o jar montado.
    """
    base_url, _ = _live_server
    criados = []

    def _make(**cookies):
        ac = httpx.AsyncClient(base_url=base_url, timeout=10, cookies=cookies)
        criados.append(ac)
        return ac

    yield _make

    for ac in criados:
        await ac.aclose()


def _set_cookie_de(res, nome: str) -> str:
    """O header Set-Cookie cru do cookie pedido — as flags só aparecem nele."""
    for raw in res.headers.get_list("set-cookie"):
        if raw.startswith(f"{nome}="):
            return raw
    raise AssertionError(f"Set-Cookie de {nome} ausente: {res.headers.get_list('set-cookie')}")


class TestCookiesDoLogin:
    async def test_login_seta_o_cookie_do_token(self, login_response):
        assert login_response.cookies.get(ADMIN_TOKEN_COOKIE)

    async def test_cookie_do_token_e_httponly(self, login_response):
        """O ponto central da migração: o JS não pode ler o JWT."""
        assert "httponly" in _set_cookie_de(login_response, ADMIN_TOKEN_COOKIE).lower()

    async def test_cookie_do_token_e_samesite_strict(self, login_response):
        raw = _set_cookie_de(login_response, ADMIN_TOKEN_COOKIE).lower()
        assert "samesite=strict" in raw

    async def test_cookie_de_csrf_nao_e_httponly(self, login_response):
        """
        Este precisa ser legível — o admin.js copia o valor para o header
        X-CSRF-Token. Não é credencial: sozinho não autentica nada.
        """
        assert "httponly" not in _set_cookie_de(login_response, ADMIN_CSRF_COOKIE).lower()

    async def test_cookie_de_csrf_e_samesite_strict(self, login_response):
        raw = _set_cookie_de(login_response, ADMIN_CSRF_COOKIE).lower()
        assert "samesite=strict" in raw

    async def test_token_continua_no_corpo_para_clientes_bearer(self, login_response):
        """Scripts, curl e o job do CI não têm cookie jar."""
        assert login_response.json()["access_token"]


class TestAutenticacaoPorCookie:
    async def test_get_autenticado_so_com_cookie(self, cliente_com_cookies, admin_token):
        """Sem header Authorization nenhum."""
        ac = cliente_com_cookies(**{ADMIN_TOKEN_COOKIE: admin_token})
        assert (await ac.get("/api/admin/stats")).status_code == 200

    async def test_cookie_invalido_rejeitado(self, cliente_com_cookies):
        ac = cliente_com_cookies(**{ADMIN_TOKEN_COOKIE: "nao-e-um-jwt"})
        assert (await ac.get("/api/admin/stats")).status_code == 401


class TestCsrf:
    """
    O alvo é POST/PUT autenticado por cookie. GET não passa pela checagem
    (as rotas de exportação são GET e só leem).
    """

    async def test_post_por_cookie_sem_header_csrf_e_bloqueado(
        self, cliente_com_cookies, admin_token
    ):
        ac = cliente_com_cookies(
            **{ADMIN_TOKEN_COOKIE: admin_token, ADMIN_CSRF_COOKIE: "valor-csrf"}
        )
        assert (await ac.post("/api/admin/candidatos")).status_code == 403

    async def test_post_por_cookie_com_header_csrf_errado_e_bloqueado(
        self, cliente_com_cookies, admin_token
    ):
        """O cenário do atacante: ele dispara a requisição mas não lê o cookie."""
        ac = cliente_com_cookies(
            **{ADMIN_TOKEN_COOKIE: admin_token, ADMIN_CSRF_COOKIE: "valor-csrf"}
        )
        res = await ac.post(
            "/api/admin/candidatos", headers={"X-CSRF-Token": "chute-do-atacante"}
        )
        assert res.status_code == 403

    async def test_post_por_cookie_sem_cookie_de_csrf_e_bloqueado(
        self, cliente_com_cookies, admin_token
    ):
        """Mandar só o header, sem o cookie, não pode bastar."""
        ac = cliente_com_cookies(**{ADMIN_TOKEN_COOKIE: admin_token})
        res = await ac.post("/api/admin/candidatos", headers={"X-CSRF-Token": "valor-csrf"})
        assert res.status_code == 403

    async def test_post_por_cookie_com_csrf_correto_passa(self, cliente_com_cookies, admin_token):
        ac = cliente_com_cookies(
            **{ADMIN_TOKEN_COOKIE: admin_token, ADMIN_CSRF_COOKIE: "valor-csrf"}
        )
        res = await ac.post(
            "/api/admin/candidatos",
            headers={"X-CSRF-Token": "valor-csrf"},
            data={"nome": "Candidato CSRF", "apelido": "CSRF"},
        )
        assert res.status_code == 200

    async def test_put_por_cookie_sem_csrf_e_bloqueado(self, cliente_com_cookies, admin_token):
        ac = cliente_com_cookies(
            **{ADMIN_TOKEN_COOKIE: admin_token, ADMIN_CSRF_COOKIE: "valor-csrf"}
        )
        res = await ac.put("/api/admin/candidatos/1", data={"ativo": "false"})
        assert res.status_code == 403

    async def test_get_por_cookie_nao_exige_csrf(self, cliente_com_cookies, admin_token):
        ac = cliente_com_cookies(
            **{ADMIN_TOKEN_COOKIE: admin_token, ADMIN_CSRF_COOKIE: "valor-csrf"}
        )
        assert (await ac.get("/api/admin/stats")).status_code == 200

    @pytest.mark.parametrize("rota", ["/api/admin/export/csv", "/api/admin/export/excel"])
    async def test_exportacoes_continuam_funcionando_por_cookie(
        self, cliente_com_cookies, admin_token, rota
    ):
        ac = cliente_com_cookies(**{ADMIN_TOKEN_COOKIE: admin_token})
        assert (await ac.get(rota)).status_code == 200


class TestBearerContinuaValendo:
    """
    O header Authorization segue aceito para clientes fora do navegador.
    CSRF não se aplica a eles: nenhum navegador anexa Authorization
    sozinho numa requisição cross-site, que é o que torna o CSRF possível
    com cookie.
    """

    async def test_get_por_bearer(self, client, admin_token):
        res = await client.get(
            "/api/admin/stats", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert res.status_code == 200

    async def test_post_por_bearer_nao_exige_csrf(self, client, admin_token):
        res = await client.post(
            "/api/admin/candidatos",
            headers={"Authorization": f"Bearer {admin_token}"},
            data={"nome": "Candidato Bearer", "apelido": "Bearer"},
        )
        assert res.status_code == 200


class TestLogout:
    async def test_logout_apaga_os_dois_cookies(self, cliente_com_cookies, admin_token):
        ac = cliente_com_cookies(
            **{ADMIN_TOKEN_COOKIE: admin_token, ADMIN_CSRF_COOKIE: "valor-csrf"}
        )
        res = await ac.post("/api/admin/logout", headers={"X-CSRF-Token": "valor-csrf"})
        assert res.status_code == 200

        apagados = " ".join(res.headers.get_list("set-cookie"))
        assert ADMIN_TOKEN_COOKIE in apagados
        assert ADMIN_CSRF_COOKIE in apagados

    async def test_logout_nao_exige_autenticacao(self, client):
        """Um 401 aqui deixaria o usuário preso com um cookie que ele não limpa."""
        res = await client.post("/api/admin/logout")
        assert res.status_code == 200
