class TestValidateCpf:
    async def test_valid_available_cpf(self, client, valid_cpf):
        res = await client.post("/api/survey/validate-cpf", json={"cpf": valid_cpf()})
        assert res.status_code == 200
        body = res.json()
        assert body["valid"] is True
        assert body["available"] is True

    async def test_invalid_cpf_rejected(self, client):
        res = await client.post("/api/survey/validate-cpf", json={"cpf": "123.456.789-00"})
        # O validador Pydantic recusa o CPF na camada de schema (422) antes
        # de chegar no handler — nunca retorna 200 com valid:false.
        assert res.status_code == 422

    async def test_cpf_already_submitted_is_unavailable(
        self, client, db_session, valid_cpf, numero_socio
    ):
        from app.models import Associado
        from app.utils.cpf import normalize_cpf

        cpf = valid_cpf()
        db_session.add(
            Associado(
                nome="Alguém",
                cpf=normalize_cpf(cpf),
                telefone="11988887777",
                numero_socio=numero_socio(),
                aceite_lgpd=True,
            )
        )
        await db_session.commit()

        res = await client.post("/api/survey/validate-cpf", json={"cpf": cpf})
        body = res.json()
        assert body["valid"] is True
        assert body["available"] is False
