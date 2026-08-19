from app.core.config import get_settings
from app.core.limiter import limiter

# Importar os módulos de rota popula limiter._route_limits neste processo.
# O processo de teste nunca importa app.main (ver o comentário no topo de
# tests/conftest.py) — o app roda num subprocesso uvicorn —, então sem
# estes imports o registro do slowapi fica vazio aqui e as asserções de
# TestRateLimitVemDeSettings estouram KeyError.
from app.api.routes import admin as _admin_routes  # noqa: F401,E402
from app.api.routes import survey as _survey_routes  # noqa: F401,E402


def _limite_configurado() -> int:
    """Quantidade de RATE_LIMIT_ADMIN_LOGIN ("6/minute" -> 6)."""
    return int(get_settings().rate_limit_admin_login.partition("/")[0].strip())


class TestAdminLoginRateLimit:
    """
    Regressão do achado A3 da auditoria: a rota de login admin não tinha
    rate limit dedicado, caindo no default genérico (60/minuto) — brute
    force viável. Corrigido com um @limiter.limit() direto na rota.

    Este teste confirma que o 429 aparece em algum momento — não conta um
    número exato de tentativas "boas" antes do bloqueio, porque outros
    testes da mesma sessão também chamam /api/admin/login e compartilham a
    mesma janela de 1 minuto (rate limit é por IP, e todos os testes batem
    do mesmo IP local). Contar tentativas exatas tornaria este teste
    frágil à ordem de execução da suíte.

    A rajada é dimensionada a partir do limite configurado, e não fixa em
    8: fixa, o teste passava na suíte inteira (onde os logins anteriores
    já consumiram parte da janela) e falhava ao rodar só este arquivo, se
    o limite fosse igual ou maior que a rajada. `pytest
    tests/security/` é um comando documentado no CLAUDE.md e precisa
    funcionar isolado.
    """

    async def test_login_gets_rate_limited_eventually(self, client):
        tentativas = _limite_configurado() + 4
        statuses = []
        for _ in range(tentativas):
            res = await client.post(
                "/api/admin/login", json={"username": "admin", "password": "senhaerrada"}
            )
            statuses.append(res.status_code)

        assert 429 in statuses, (
            f"Nenhuma resposta 429 em {tentativas} tentativas com limite "
            f"{_limite_configurado()}/minuto: {statuses}"
        )


class TestRateLimitVemDeSettings:
    """
    O limite do login precisa vir de RATE_LIMIT_ADMIN_LOGIN, não de uma
    string hardcodada na rota.

    Por que este teste existe separado do de cima: durante um tempo a rota
    tinha `@limiter.limit("5/minute")` fixo enquanto a setting existia,
    estava documentada no .env.example e era silenciosamente ignorada — ou
    seja, dava para "ajustar" o limite no .env sem efeito nenhum. E o teste
    de comportamento acima **passava assim mesmo**: tanto o valor
    hardcodado quanto o configurado ficam abaixo do total de tentativas de
    login da suíte, então os dois produzem 429 em algum momento. Nenhuma
    asserção sobre status HTTP separa os dois casos de forma estável,
    porque a janela é compartilhada com os outros testes que fazem login.

    Daí a checagem ser sobre o que o slowapi registrou para a rota. É API
    privada (`_route_limits`), o que normalmente eu evitaria num teste —
    mas é o que torna a verificação independente da ordem de execução, e a
    alternativa (contar respostas numa janela compartilhada) já se provou
    incapaz de pegar exatamente o bug que este teste existe para pegar.
    """

    ROTA_LOGIN = "app.api.routes.admin.admin_login"

    @staticmethod
    def _quantidade_registrada(rota: str) -> str:
        """Primeiro token de algo como "8 per 1 minute"."""
        limites = limiter._route_limits[rota]
        assert len(limites) == 1, f"Esperado um único limite em {rota}, veio {limites}"
        return str(limites[0].limit).split(" ", 1)[0]

    def test_limite_do_login_bate_com_a_configuracao(self):
        configurado = get_settings().rate_limit_admin_login  # "8/minute" no conftest
        esperado = configurado.partition("/")[0].strip()
        registrado = self._quantidade_registrada(self.ROTA_LOGIN)

        assert registrado == esperado, (
            f"A rota de login está limitada a {registrado}/minuto, mas "
            f"RATE_LIMIT_ADMIN_LOGIN={configurado}. O limite provavelmente "
            f"voltou a ser hardcodado em app/api/routes/admin.py."
        )

    def test_limites_do_fluxo_publico_batem_com_a_configuracao(self):
        """
        As rotas de survey.py já liam de Settings — este teste trava o
        comportamento para as duas famílias de rota, não só para o login.
        """
        settings = get_settings()
        esperado = {
            "app.api.routes.survey.validate_cpf_endpoint": settings.rate_limit_validate_cpf,
            "app.api.routes.survey.register": settings.rate_limit_register,
            "app.api.routes.survey.verify_otp": settings.rate_limit_verify_otp,
            "app.api.routes.survey.resend_otp": settings.rate_limit_resend_otp,
            "app.api.routes.survey.submit_vote": settings.rate_limit_submit,
        }

        for rota, configurado in esperado.items():
            registrado = self._quantidade_registrada(rota)
            assert registrado == configurado.partition("/")[0].strip(), (
                f"{rota} está limitada a {registrado}/minuto, esperado {configurado}"
            )
