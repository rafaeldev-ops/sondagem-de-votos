"""
Regressão dos headers de segurança aplicados por SecurityHeadersMiddleware
e RequestIdMiddleware (ambos BaseHTTPMiddleware).

Motivo de existir: a suíte cobria o corpo das respostas, mas nada afirmava
sobre os headers. Um BaseHTTPMiddleware que pare de rodar — por mudança de
comportamento entre versões do starlette, ou por alguém remover o
add_middleware em app/main.py — não quebraria nenhum outro teste: a API
continua respondendo 200 normalmente, só sem CSP, sem X-Frame-Options e
sem X-Request-ID. O upgrade starlette 0.41 -> 1.3 foi feito exatamente com
esse risco em mente; estes testes são a rede que faltava.
"""


class TestSecurityHeaders:
    async def test_headers_basicos_presentes(self, client):
        res = await client.get("/health")
        assert res.status_code == 200
        assert res.headers["X-Content-Type-Options"] == "nosniff"
        assert res.headers["X-Frame-Options"] == "DENY"
        assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "camera=()" in res.headers["Permissions-Policy"]

    async def test_csp_presente_e_restritiva(self, client):
        res = await client.get("/health")
        csp = res.headers["Content-Security-Policy"]

        assert "default-src 'self'" in csp
        assert "object-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "base-uri 'self'" in csp

    async def test_script_src_nao_permite_unsafe_inline(self, client):
        """
        script-src com 'unsafe-inline' reabriria o XSS armazenado (achado C1)
        mesmo com a sanitização no service: bastaria um ponto de escape na
        sanitização para o payload voltar a executar. O admin.js usa event
        delegation em vez de onclick= justamente para não precisar disso.
        """
        res = await client.get("/health")
        csp = res.headers["Content-Security-Policy"]

        script_src = next(d for d in csp.split(";") if d.strip().startswith("script-src"))
        assert "'unsafe-inline'" not in script_src
        assert "'unsafe-eval'" not in script_src

    async def test_style_src_nao_permite_unsafe_inline(self, client):
        """
        Os estilos inline dos templates viraram classes (.flow-shell no
        fluxo público, .login-card no admin) para permitir remover
        'unsafe-inline' daqui — e o
        progresso das etapas, que era uma barra ajustada por
        element.style.width, virou bolinhas cujo estado é classList.
        Sem 'unsafe-inline', HTML injetado não consegue usar CSS para sobrepor a
        página com um formulário falso nem exfiltrar conteúdo por seletor
        de atributo + background-image.

        Se alguém reintroduzir um style="..." num template e afrouxar a CSP
        de volta para fazê-lo funcionar, este teste falha.
        """
        res = await client.get("/health")
        csp = res.headers["Content-Security-Policy"]

        style_src = next(d for d in csp.split(";") if d.strip().startswith("style-src"))
        assert "'unsafe-inline'" not in style_src

    async def test_templates_nao_tem_atributo_style(self, client):
        """
        Bate na causa raiz, não no sintoma: com style-src sem
        'unsafe-inline', qualquer style="" que volte aos templates é
        silenciosamente ignorado pelo navegador — o layout quebra sem erro
        de servidor e sem nenhum teste de status falhar.
        """
        for rota in ("/", "/admin"):
            html = (await client.get(rota)).text
            assert 'style="' not in html, f"atributo style= reintroduzido em {rota}"

    async def test_rotas_admin_nao_ficam_em_cache(self, client):
        """Respostas da API admin podem conter CPF/telefone de associados."""
        res = await client.get("/api/admin/stats")
        assert res.headers["Cache-Control"] == "no-store"


class TestRequestId:
    async def test_request_id_presente_na_resposta(self, client):
        res = await client.get("/health")
        assert res.headers.get("X-Request-ID")

    async def test_request_id_do_cliente_e_reaproveitado(self, client):
        """Permite correlacionar um erro reportado pelo usuário com os logs."""
        res = await client.get("/health", headers={"X-Request-ID": "id-de-teste-123"})
        assert res.headers["X-Request-ID"] == "id-de-teste-123"

    async def test_request_ids_sao_distintos_entre_requisicoes(self, client):
        primeiro = (await client.get("/health")).headers["X-Request-ID"]
        segundo = (await client.get("/health")).headers["X-Request-ID"]
        assert primeiro != segundo
