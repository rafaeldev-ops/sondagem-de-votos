"""
As duas páginas HTML servidas por Jinja: / (fluxo público) e /admin.

Motivo de existir: a suíte só batia em rotas de API e em /health. As
páginas renderizadas nunca eram requisitadas por nenhum teste, então
qualquer erro de renderização passava despercebido — foi exatamente o que
aconteceu no upgrade starlette 0.41 -> 1.3, que mudou a assinatura de
TemplateResponse (o request virou o primeiro argumento posicional). Os 71
testes ficaram verdes e as duas páginas devolviam 500; só apareceu ao
abrir a aplicação de verdade no container.
"""


class TestPaginaPublica:
    async def test_index_renderiza(self, client):
        res = await client.get("/")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]

    async def test_index_tem_todas_as_etapas(self, client):
        """cadastro -> OTP -> candidatos -> ponto focal -> modalidades ->
        LGPD, mais o agradecimento. Se uma sumir do template, o fluxo trava
        numa etapa que não existe e o goToStep() quebra em runtime."""
        html = (await client.get("/")).text
        for step in ("step1", "step2", "step3", "step4", "step5", "step6", "stepThanks"):
            assert f'id="{step}"' in html

    async def test_index_interpola_o_contexto(self, client):
        """
        app_name vem do contexto do template. Se o contexto não chegar ao
        Jinja, o título fica vazio em vez de quebrar — por isso a asserção
        é no valor, não só no status 200.
        """
        html = (await client.get("/")).text
        assert "SEMPRE TRICOLOR" in html

    async def test_index_carrega_o_js_do_fluxo(self, client):
        html = (await client.get("/")).text
        assert "/static/js/app.js" in html

    async def test_index_tem_campo_de_numero_de_socio(self, client):
        """O cadastro passou a exigir o número de sócio; se o input sumir do
        template, o formulário quebra com 422 e só apareceria em produção."""
        html = (await client.get("/")).text
        assert 'id="numeroSocio"' in html
        assert 'maxlength="4"' in html

    async def test_index_tem_a_etapa_de_modalidades(self, client):
        """A etapa vive entre o ponto focal e o LGPD; se sumir do template,
        o fluxo quebra com 422 no submit e só apareceria em produção."""
        html = (await client.get("/")).text
        assert 'id="departamentosLista"' in html
        assert 'id="departamentosBusca"' in html
        assert 'id="departamentoOutros"' in html

    async def test_ponto_focal_tem_etapa_propria(self, client):
        """O ponto focal saiu de dentro da etapa de candidatos e virou a 4,
        o que empurrou modalidades para 5 e LGPD para 6. A contagem no rótulo
        e a quantidade de bolinhas precisam acompanhar — as três informações
        são a mesma coisa escrita em lugares diferentes."""
        html = (await client.get("/")).text
        assert 'id="focalLista"' in html
        assert 'id="btnFocal"' in html
        assert "Etapa 1 de 6" in html
        # O <select> antigo não pode sobreviver junto: dois controles para o
        # mesmo dado é como o submit passa a mandar o valor errado.
        assert 'id="preferido"' not in html

    async def test_cabecalho_tem_sondagem_2026_acima_do_wordmark(self, client):
        """A ordem importa: "Sondagem 2026" fica ACIMA do nome do clube. Uma
        troca de posição não quebra nada funcionalmente, então só um teste de
        ordem pega a regressão."""
        html = (await client.get("/")).text
        assert "Sondagem" in html
        assert "2026" in html
        assert html.index("brand-title") < html.index("brand-wordmark")

    async def test_progresso_tem_cinco_bolinhas(self, client):
        """Uma bolinha por etapa. Se o template ganhar uma etapa e ninguém
        acrescentar a bolinha, o cabeçalho passa a contar errado — e isso é
        silencioso, porque o app.js só mexe nas que existem."""
        html = (await client.get("/")).text
        assert 'id="stepDots"' in html
        assert html.count('class="step-dot"') == 6
        for etapa in range(1, 7):
            assert f'data-step="{etapa}"' in html


class TestPaginaAdmin:
    async def test_admin_renderiza(self, client):
        res = await client.get("/admin")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]

    async def test_admin_tem_login_e_dashboard(self, client):
        html = (await client.get("/admin")).text
        assert 'id="loginSection"' in html
        assert 'id="dashboardSection"' in html

    async def test_admin_interpola_o_contexto(self, client):
        html = (await client.get("/admin")).text
        assert "SEMPRE TRICOLOR" in html

    async def test_admin_carrega_o_js_do_painel(self, client):
        html = (await client.get("/admin")).text
        assert "/static/js/admin.js" in html


class TestVersaoDosEstaticos:
    """
    CSS e JS saem com `?v=<hash>` nos dois templates.

    Sem isso o navegador reaproveita o arquivo em cache e mistura HTML novo
    com script velho — pior do que só ficar com o visual antigo. Um app.js
    de uma versão anterior procura elementos que o HTML novo não tem, o
    acesso estoura TypeError no topo do arquivo e NENHUM handler é
    registrado: a página carrega inteira e nada responde ao clique.
    """

    async def test_index_versiona_css_e_js(self, client):
        html = (await client.get("/")).text
        assert "/static/css/style.css?v=" in html
        assert "/static/js/app.js?v=" in html

    async def test_admin_versiona_css_e_js(self, client):
        html = (await client.get("/admin")).text
        assert "/static/css/admin.css?v=" in html
        assert "/static/js/admin.js?v=" in html

    async def test_a_versao_nao_e_vazia(self, client):
        """`?v=` sozinho não invalida cache nenhum — seria um placeholder que
        parece resolvido e não faz nada."""
        import re

        html = (await client.get("/")).text
        versoes = re.findall(r"/static/[^\"']+\?v=([^\"'&]*)", html)
        assert versoes, "nenhum estático versionado no index"
        for v in versoes:
            assert len(v) >= 8, f"versão curta demais para ser um hash: {v!r}"

    async def test_as_duas_paginas_usam_a_mesma_versao(self, client):
        """A versão é do conjunto de estáticos, não por arquivo: se as duas
        páginas divergirem, o valor virou algo por-requisição (timestamp,
        random) e o cache nunca mais é reaproveitado."""
        import re

        padrao = r"/static/[^\"']+\?v=([^\"'&]*)"
        do_index = set(re.findall(padrao, (await client.get("/")).text))
        do_admin = set(re.findall(padrao, (await client.get("/admin")).text))
        assert len(do_index) == 1
        assert do_index == do_admin


class TestEstaticos:
    async def test_css_do_fluxo_publico(self, client):
        res = await client.get("/static/css/style.css")
        assert res.status_code == 200

    async def test_css_do_admin(self, client):
        res = await client.get("/static/css/admin.css")
        assert res.status_code == 200

    async def test_js_do_fluxo_publico(self, client):
        res = await client.get("/static/js/app.js")
        assert res.status_code == 200

    async def test_js_do_admin(self, client):
        res = await client.get("/static/js/admin.js")
        assert res.status_code == 200
