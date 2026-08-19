"""
O checkbox "sou titular do título" da etapa 1.

O campo tem três estados que precisam continuar distinguíveis ponta a ponta:
True (declarou que é titular), False (declarou que não é) e NULL (respondeu
antes da pergunta existir). O erro fácil aqui é achatar os dois últimos num
"Não" só — é isso que a maior parte destes testes vigia.
"""

from sqlalchemy import select

from app.models import Associado, Candidato


async def _votar(
    client,
    db_session,
    valid_cpf,
    numero_socio,
    read_otp_code,
    departamentos,
    telefone,
    titular,
):
    """Fluxo público completo com um valor de `titular`, até o /submit."""
    deps = await departamentos(quantos=1, com_outros=False)

    candidato = Candidato(nome="Fulano", apelido="Fu", ativo=True)
    db_session.add(candidato)
    await db_session.commit()
    await db_session.refresh(candidato)

    res = await client.post(
        "/api/survey/register",
        json={
            "nome": "Socio Titular",
            "cpf": valid_cpf(),
            "telefone": telefone,
            "numero_socio": numero_socio(),
            "titular": titular,
            "recaptcha_token": "",
        },
    )
    assert res.status_code == 200, res.text
    token = res.json()["session_token"]

    codigo = read_otp_code(telefone)
    await client.post(
        "/api/survey/verify-otp",
        json={"session_token": token, "telefone": telefone, "codigo": codigo},
    )

    res = await client.post(
        "/api/survey/submit",
        json={
            "session_token": token,
            "candidatos_ids": [candidato.id],
            "candidato_preferido_id": candidato.id,
            "departamentos_ids": [deps[0].id],
            "aceite_lgpd": True,
        },
    )
    assert res.status_code == 200, res.text
    return res


class TestCadastro:
    async def test_titular_e_obrigatorio_no_cadastro(
        self, client, valid_cpf, numero_socio
    ):
        """Sem default no schema: cadastro que não manda o campo é bug de
        frontend e precisa falhar alto, não gravar um False que ninguém
        respondeu."""
        res = await client.post(
            "/api/survey/register",
            json={
                "nome": "Socio Sem Titular",
                "cpf": valid_cpf(),
                "telefone": "11955550001",
                "numero_socio": numero_socio(),
                "recaptcha_token": "",
            },
        )
        assert res.status_code == 422

    async def test_titular_true_chega_ao_banco(
        self,
        client,
        db_session,
        valid_cpf,
        numero_socio,
        read_otp_code,
        departamentos,
    ):
        await _votar(
            client, db_session, valid_cpf, numero_socio, read_otp_code,
            departamentos, "11955550002", titular=True,
        )

        associado = (await db_session.execute(select(Associado))).scalars().one()
        assert associado.titular is True

    async def test_titular_false_grava_false_e_nao_nulo(
        self,
        client,
        db_session,
        valid_cpf,
        numero_socio,
        read_otp_code,
        departamentos,
    ):
        """Desmarcar é uma resposta. Se isso virasse NULL, a resposta de quem
        se declarou dependente ficaria indistinguível de quem nunca viu a
        pergunta, e a exportação mostraria célula vazia para os dois."""
        await _votar(
            client, db_session, valid_cpf, numero_socio, read_otp_code,
            departamentos, "11955550003", titular=False,
        )

        associado = (await db_session.execute(select(Associado))).scalars().one()
        assert associado.titular is False
        assert associado.titular is not None


class TestExportacoes:
    async def test_csv_tem_a_coluna_titular(
        self,
        client,
        db_session,
        valid_cpf,
        numero_socio,
        read_otp_code,
        departamentos,
        admin_token,
    ):
        await _votar(
            client, db_session, valid_cpf, numero_socio, read_otp_code,
            departamentos, "11955550006", titular=True,
        )

        res = await client.get(
            "/api/admin/export/csv",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        linhas = res.text.strip().split("\n")
        cabecalho = linhas[0].split(",")
        assert "Titular" in cabecalho
        assert linhas[1].split(",")[cabecalho.index("Titular")] == "Sim"

    async def test_csv_do_nao_titular_diz_nao(
        self,
        client,
        db_session,
        valid_cpf,
        numero_socio,
        read_otp_code,
        departamentos,
        admin_token,
    ):
        await _votar(
            client, db_session, valid_cpf, numero_socio, read_otp_code,
            departamentos, "11955550007", titular=False,
        )

        res = await client.get(
            "/api/admin/export/csv",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        linhas = res.text.strip().split("\n")
        cabecalho = linhas[0].split(",")
        assert linhas[1].split(",")[cabecalho.index("Titular")] == "Não"

    async def test_resposta_anterior_a_pergunta_exporta_vazio(
        self, client, db_session, valid_cpf, admin_token
    ):
        """Linha com titular IS NULL — o que a migration 007 deixa para trás.
        Célula vazia, nunca "Não": ninguém respondeu essa pergunta, e um
        "Não" aqui contaria essa pessoa como dependente na análise."""
        db_session.add(
            Associado(
                nome="Socio Antigo",
                cpf=valid_cpf(),
                numero_socio="9999",
                telefone="11955550008",
                titular=None,
                aceite_lgpd=True,
            )
        )
        await db_session.commit()

        res = await client.get(
            "/api/admin/export/csv",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        linhas = res.text.strip().split("\n")
        cabecalho = linhas[0].split(",")
        assert linhas[1].split(",")[cabecalho.index("Titular")] == ""


class TestPaginaPublica:
    async def test_o_checkbox_esta_na_etapa_1(self, client):
        """Se o input sumir do template, o cadastro passa a mandar payload
        sem `titular` e o fluxo inteiro quebra com 422 já na primeira etapa."""
        html = (await client.get("/")).text
        assert 'id="titular"' in html
        assert "Sou titular do título" in html
