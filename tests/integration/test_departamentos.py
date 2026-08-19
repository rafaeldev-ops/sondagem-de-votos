"""
A lista de modalidades é populada por migration, mas os testes criam o
schema com create_all e NÃO rodam migrations — então aqui cada teste cria
as suas próprias linhas, como já se faz com candidatos.
"""


async def _preparar_voto(
    client, db_session, valid_cpf, numero_socio, read_otp_code, telefone
):
    """Cria um candidato e leva a sessão até logo antes do /submit,
    devolvendo (session_token, candidato_id)."""
    from app.models import Candidato

    candidato = Candidato(nome="Fulano", apelido="Fu", ativo=True)
    db_session.add(candidato)
    await db_session.commit()
    await db_session.refresh(candidato)

    res = await client.post(
        "/api/survey/register",
        json={
            "nome": "Socio Modalidades",
            "cpf": valid_cpf(),
            "telefone": telefone,
            "numero_socio": numero_socio(),
            "titular": True,
            "recaptcha_token": "",
        },
    )
    token = res.json()["session_token"]
    codigo = read_otp_code(telefone)
    await client.post(
        "/api/survey/verify-otp",
        json={"session_token": token, "telefone": telefone, "codigo": codigo},
    )
    return token, candidato.id


class TestListagemDeDepartamentos:
    async def test_lista_apenas_ativos(self, client, departamentos):
        await departamentos(quantos=3, com_outros=False)

        res = await client.get("/api/survey/departamentos")
        assert res.status_code == 200
        assert len(res.json()) == 3
        assert {"id", "nome"} == set(res.json()[0].keys())

    async def test_respeita_a_coluna_ordem_e_nao_o_nome(self, client, db_session):
        """A ordem é um dado, não alfabética: sob a collation do banco,
        ORDER BY nome devolveria outra sequência."""
        from app.models import Departamento

        db_session.add_all(
            [
                Departamento(nome="Zumba", ordem=1, ativo=True),
                Departamento(nome="Atletismo", ordem=2, ativo=True),
                Departamento(nome="Outros", ordem=999, exige_texto=True, ativo=True),
            ]
        )
        await db_session.commit()

        nomes = [d["nome"] for d in (await client.get("/api/survey/departamentos")).json()]
        assert nomes == ["Zumba", "Atletismo", "Outros"]

    async def test_inativo_nao_aparece(self, client, db_session):
        from app.models import Departamento

        db_session.add_all(
            [
                Departamento(nome="Ativa", ordem=1, ativo=True),
                Departamento(nome="Encerrada", ordem=2, ativo=False),
            ]
        )
        await db_session.commit()

        nomes = [d["nome"] for d in (await client.get("/api/survey/departamentos")).json()]
        assert nomes == ["Ativa"]


class TestSubmitComDepartamentos:
    async def test_submit_sem_nenhuma_modalidade_e_recusado(
        self, client, db_session, valid_cpf, numero_socio, read_otp_code, departamentos
    ):
        await departamentos()
        token, cid = await _preparar_voto(
            client, db_session, valid_cpf, numero_socio, read_otp_code, "11933330001"
        )

        res = await client.post(
            "/api/survey/submit",
            json={
                "session_token": token,
                "candidatos_ids": [cid],
                "candidato_preferido_id": cid,
                "departamentos_ids": [],
                "aceite_lgpd": True,
            },
        )
        assert res.status_code == 422

    async def test_modalidade_inexistente_e_recusada(
        self, client, db_session, valid_cpf, numero_socio, read_otp_code, departamentos
    ):
        await departamentos()
        token, cid = await _preparar_voto(
            client, db_session, valid_cpf, numero_socio, read_otp_code, "11933330002"
        )

        res = await client.post(
            "/api/survey/submit",
            json={
                "session_token": token,
                "candidatos_ids": [cid],
                "candidato_preferido_id": cid,
                "departamentos_ids": [999999],
                "aceite_lgpd": True,
            },
        )
        assert res.status_code == 400
        assert "modalidade" in res.json()["detail"].lower()

    async def test_modalidade_inativa_e_recusada(
        self, client, db_session, valid_cpf, numero_socio, read_otp_code
    ):
        from app.models import Departamento

        inativa = Departamento(nome="Encerrada", ordem=1, ativo=False)
        db_session.add(inativa)
        await db_session.commit()
        await db_session.refresh(inativa)

        token, cid = await _preparar_voto(
            client, db_session, valid_cpf, numero_socio, read_otp_code, "11933330003"
        )

        res = await client.post(
            "/api/survey/submit",
            json={
                "session_token": token,
                "candidatos_ids": [cid],
                "candidato_preferido_id": cid,
                "departamentos_ids": [inativa.id],
                "aceite_lgpd": True,
            },
        )
        assert res.status_code == 400

    async def test_outros_sem_texto_e_recusado(
        self, client, db_session, valid_cpf, numero_socio, read_otp_code, departamentos
    ):
        deps = await departamentos()
        outros = deps[-1]
        token, cid = await _preparar_voto(
            client, db_session, valid_cpf, numero_socio, read_otp_code, "11933330004"
        )

        res = await client.post(
            "/api/survey/submit",
            json={
                "session_token": token,
                "candidatos_ids": [cid],
                "candidato_preferido_id": cid,
                "departamentos_ids": [outros.id],
                "departamento_outros": "   ",
                "aceite_lgpd": True,
            },
        )
        assert res.status_code == 400
        assert "outros" in res.json()["detail"].lower()

    async def test_caminho_feliz_grava_as_modalidades_e_o_texto(
        self, client, db_session, valid_cpf, numero_socio, read_otp_code, departamentos
    ):
        from sqlalchemy import select

        from app.models import Associado

        deps = await departamentos()
        escolhidas = [deps[0].id, deps[-1].id]
        token, cid = await _preparar_voto(
            client, db_session, valid_cpf, numero_socio, read_otp_code, "11933330005"
        )

        res = await client.post(
            "/api/survey/submit",
            json={
                "session_token": token,
                "candidatos_ids": [cid],
                "candidato_preferido_id": cid,
                "departamentos_ids": escolhidas,
                "departamento_outros": "Xadrez",
                "aceite_lgpd": True,
            },
        )
        assert res.status_code == 200

        result = await db_session.execute(
            select(Associado).where(Associado.telefone == "11933330005")
        )
        associado = result.scalar_one()
        await db_session.refresh(associado, ["departamentos"])
        assert {d.departamento_id for d in associado.departamentos} == set(escolhidas)
        assert associado.departamento_outros == "Xadrez"

    async def test_texto_sem_outros_marcado_e_descartado(
        self, client, db_session, valid_cpf, numero_socio, read_otp_code, departamentos
    ):
        """Não se guarda texto órfão de quem preencheu o campo e depois
        desmarcou "Outros"."""
        from sqlalchemy import select

        from app.models import Associado

        deps = await departamentos()
        token, cid = await _preparar_voto(
            client, db_session, valid_cpf, numero_socio, read_otp_code, "11933330006"
        )

        res = await client.post(
            "/api/survey/submit",
            json={
                "session_token": token,
                "candidatos_ids": [cid],
                "candidato_preferido_id": cid,
                "departamentos_ids": [deps[0].id],
                "departamento_outros": "Xadrez",
                "aceite_lgpd": True,
            },
        )
        assert res.status_code == 200

        result = await db_session.execute(
            select(Associado).where(Associado.telefone == "11933330006")
        )
        assert result.scalar_one().departamento_outros is None
