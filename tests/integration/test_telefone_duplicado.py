"""
O telefone recebe o código OTP e identifica o dono da resposta do mesmo
jeito que CPF e número de sócio: um número só pode participar uma vez da
sondagem.
"""


class TestUnicidadeDoTelefone:
    async def test_telefone_repetido_e_barrado_antes_de_enviar_otp(
        self, client, db_session, valid_cpf, numero_socio
    ):
        """
        Barrar no /register (e não só no /submit) evita gastar um SMS num
        cadastro que seria rejeitado no fim do fluxo.
        """
        from app.models import Associado

        telefone = "11933330001"
        db_session.add(
            Associado(
                nome="Ja Votou",
                cpf=valid_cpf(),
                telefone=telefone,
                numero_socio=numero_socio(),
                aceite_lgpd=True,
            )
        )
        await db_session.commit()

        res = await client.post(
            "/api/survey/register",
            json={
                "nome": "Segundo Cadastro",
                "cpf": valid_cpf(),
                "telefone": telefone,
                "numero_socio": numero_socio(),
                "titular": True,
                "recaptcha_token": "",
            },
        )
        assert res.status_code == 400
        assert "telefone" in res.json()["detail"].lower()

    async def test_cpf_repetido_continua_com_a_mensagem_de_cpf(
        self, client, db_session, valid_cpf, numero_socio
    ):
        """
        Fixa a ORDEM das checagens em register_and_send_otp (CPF antes de
        telefone): com CPF e telefone ambos repetidos, a mensagem tem que
        continuar sendo a de CPF.
        """
        from app.models import Associado

        cpf = valid_cpf()
        db_session.add(
            Associado(
                nome="Ja Votou",
                cpf=cpf,
                telefone="11933330002",
                numero_socio=numero_socio(),
                aceite_lgpd=True,
            )
        )
        await db_session.commit()

        res = await client.post(
            "/api/survey/register",
            json={
                "nome": "Outro Cadastro",
                "cpf": cpf,
                "telefone": "11933330002",
                "numero_socio": numero_socio(),
                "titular": True,
                "recaptcha_token": "",
            },
        )
        assert res.status_code == 400
        assert "CPF" in res.json()["detail"]

    async def test_telefone_diferente_prossegue_normalmente(
        self, client, valid_cpf, numero_socio
    ):
        res = await client.post(
            "/api/survey/register",
            json={
                "nome": "Cadastro Novo",
                "cpf": valid_cpf(),
                "telefone": "11933330003",
                "numero_socio": numero_socio(),
                "titular": True,
                "recaptcha_token": "",
            },
        )
        assert res.status_code == 200
        assert "session_token" in res.json()

    async def test_telefone_com_duas_linhas_legadas_nao_derruba_o_register(
        self, client, db_session, valid_cpf, numero_socio
    ):
        """
        Telefone não tem UNIQUE constraint no banco (decisão consciente: só
        checagem de aplicação, sem migration em produção). Antes dessa
        checagem existir, nada impedia duas respostas completas com o mesmo
        telefone — e isso já aconteceu em produção. get_by_telefone não pode
        presumir no máximo uma linha (scalar_one_or_none rejeita mais de
        uma), senão um telefone com histórico duplicado derruba o /register
        inteiro com 500 em vez do 400 esperado.
        """
        from app.models import Associado

        telefone = "11933330004"
        db_session.add_all(
            [
                Associado(
                    nome="Primeira Linha Legada",
                    cpf=valid_cpf(),
                    telefone=telefone,
                    numero_socio=numero_socio(),
                    aceite_lgpd=True,
                ),
                Associado(
                    nome="Segunda Linha Legada",
                    cpf=valid_cpf(),
                    telefone=telefone,
                    numero_socio=numero_socio(),
                    aceite_lgpd=True,
                ),
            ]
        )
        await db_session.commit()

        res = await client.post(
            "/api/survey/register",
            json={
                "nome": "Terceiro Cadastro",
                "cpf": valid_cpf(),
                "telefone": telefone,
                "numero_socio": numero_socio(),
                "titular": True,
                "recaptcha_token": "",
            },
        )
        assert res.status_code == 400
        assert "telefone" in res.json()["detail"].lower()
