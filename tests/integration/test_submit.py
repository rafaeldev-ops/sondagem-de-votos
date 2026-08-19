async def _register_verify(
    client, valid_cpf, numero_socio, read_otp_code, telefone, nome="Teste Fluxo"
):
    """Completa cadastro + verificação de OTP, devolvendo o session_token pronto
    para submissão — evita repetir esse bloco em cada teste de submit."""
    res = await client.post(
        "/api/survey/register",
        json={
            "nome": nome,
            "cpf": valid_cpf(),
            "telefone": telefone,
            "numero_socio": numero_socio(),
            "titular": True,
            "recaptcha_token": "",
        },
    )
    session_token = res.json()["session_token"]
    code = read_otp_code(telefone)
    await client.post(
        "/api/survey/verify-otp",
        json={"session_token": session_token, "telefone": telefone, "codigo": code},
    )
    return session_token


class TestSubmit:
    async def test_full_flow_success(
        self, client, db_session, valid_cpf, numero_socio, read_otp_code, departamentos
    ):
        from app.models import Candidato

        c1 = Candidato(nome="Fulano", apelido="Fu", ativo=True)
        c2 = Candidato(nome="Beltrano", apelido="Bel", ativo=True)
        db_session.add_all([c1, c2])
        await db_session.commit()
        await db_session.refresh(c1)
        await db_session.refresh(c2)

        deps = await departamentos(quantos=1, com_outros=False)
        dep = deps[0]

        session_token = await _register_verify(
            client, valid_cpf, numero_socio, read_otp_code, "11988888001"
        )

        res = await client.post(
            "/api/survey/submit",
            json={
                "session_token": session_token,
                "candidatos_ids": [c1.id, c2.id],
                "candidato_preferido_id": c1.id,
                "departamentos_ids": [dep.id],
                "aceite_lgpd": True,
            },
        )
        assert res.status_code == 200

    async def test_submit_without_lgpd_consent_accepted(
        self, client, db_session, valid_cpf, numero_socio, read_otp_code, departamentos
    ):
        """
        aceite_lgpd é opt-in de contato ("autorizo receber notícias"), não
        condição para participar da sondagem — desmarcado precisa continuar
        registrando o voto normalmente, do mesmo jeito que "titular"
        desmarcado é uma resposta válida.
        """
        from app.models import Candidato

        c1 = Candidato(nome="Fulano", apelido="Fu", ativo=True)
        db_session.add(c1)
        await db_session.commit()
        await db_session.refresh(c1)

        deps = await departamentos(quantos=1, com_outros=False)
        dep = deps[0]

        session_token = await _register_verify(
            client, valid_cpf, numero_socio, read_otp_code, "11988888002"
        )

        res = await client.post(
            "/api/survey/submit",
            json={
                "session_token": session_token,
                "candidatos_ids": [c1.id],
                "candidato_preferido_id": c1.id,
                "departamentos_ids": [dep.id],
                "aceite_lgpd": False,
            },
        )
        assert res.status_code == 200

    async def test_submit_more_than_20_candidatos_rejected(
        self, client, valid_cpf, numero_socio, read_otp_code, departamentos
    ):
        deps = await departamentos(quantos=1, com_outros=False)
        dep = deps[0]

        session_token = await _register_verify(
            client, valid_cpf, numero_socio, read_otp_code, "11988888003"
        )
        res = await client.post(
            "/api/survey/submit",
            json={
                "session_token": session_token,
                "candidatos_ids": list(range(1, 22)),  # 21 ids
                "candidato_preferido_id": 1,
                "departamentos_ids": [dep.id],
                "aceite_lgpd": True,
            },
        )
        # Regressão do limite adicionado no reskin (max_length=20 no schema)
        assert res.status_code == 422

    async def test_duplicate_cpf_blocked_on_second_submission(
        self, client, db_session, valid_cpf, numero_socio, read_otp_code, departamentos
    ):
        from app.models import Candidato

        c1 = Candidato(nome="Fulano", apelido="Fu", ativo=True)
        db_session.add(c1)
        await db_session.commit()
        await db_session.refresh(c1)

        deps = await departamentos(quantos=1, com_outros=False)
        dep = deps[0]

        cpf = valid_cpf()

        # Primeira pessoa usa o CPF e completa a sondagem
        res1 = await client.post(
            "/api/survey/register",
            json={
                "nome": "Primeira Pessoa",
                "cpf": cpf,
                "telefone": "11988888004",
                "numero_socio": numero_socio(),
                "titular": True,
                "recaptcha_token": "",
            },
        )
        session1 = res1.json()["session_token"]
        code1 = read_otp_code("11988888004")
        await client.post(
            "/api/survey/verify-otp",
            json={"session_token": session1, "telefone": "11988888004", "codigo": code1},
        )
        submit1 = await client.post(
            "/api/survey/submit",
            json={
                "session_token": session1,
                "candidatos_ids": [c1.id],
                "candidato_preferido_id": c1.id,
                "departamentos_ids": [dep.id],
                "aceite_lgpd": True,
            },
        )
        assert submit1.status_code == 200

        # Mesmo CPF tenta se cadastrar de novo — checagem prévia já barra
        check = await client.post("/api/survey/validate-cpf", json={"cpf": cpf})
        assert check.json()["available"] is False
