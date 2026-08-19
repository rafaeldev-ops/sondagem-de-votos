class TestOtpFlow:
    async def test_register_sends_otp(self, client, valid_cpf, numero_socio, read_otp_code):
        res = await client.post(
            "/api/survey/register",
            json={
                "nome": "Carlos Silva",
                "cpf": valid_cpf(),
                "telefone": "11988887001",
                "numero_socio": numero_socio(),
                "titular": True,
                "recaptcha_token": "",
            },
        )
        assert res.status_code == 200
        assert "session_token" in res.json()
        # Confirma que um código foi de fato gerado e "enviado" (mock)
        code = read_otp_code("11988887001")
        assert len(code) == 6

    async def test_verify_wrong_code_then_correct(
        self, client, valid_cpf, numero_socio, read_otp_code
    ):
        res = await client.post(
            "/api/survey/register",
            json={
                "nome": "Ana Souza",
                "cpf": valid_cpf(),
                "telefone": "11988887002",
                "numero_socio": numero_socio(),
                "titular": True,
                "recaptcha_token": "",
            },
        )
        session_token = res.json()["session_token"]
        code = read_otp_code("11988887002")

        wrong = await client.post(
            "/api/survey/verify-otp",
            json={"session_token": session_token, "telefone": "11988887002", "codigo": "000000"},
        )
        assert wrong.status_code == 400

        right = await client.post(
            "/api/survey/verify-otp",
            json={"session_token": session_token, "telefone": "11988887002", "codigo": code},
        )
        assert right.status_code == 200

    async def test_max_attempts_locks_out(
        self, client, valid_cpf, numero_socio, read_otp_code
    ):
        res = await client.post(
            "/api/survey/register",
            json={
                "nome": "Pedro Lima",
                "cpf": valid_cpf(),
                "telefone": "11988887003",
                "numero_socio": numero_socio(),
                "titular": True,
                "recaptcha_token": "",
            },
        )
        session_token = res.json()["session_token"]

        # OTP_MAX_ATTEMPTS=5 no ambiente de teste — a 6a tentativa (mesmo com
        # o código certo) já deveria estar bloqueada.
        for _ in range(5):
            wrong = await client.post(
                "/api/survey/verify-otp",
                json={
                    "session_token": session_token,
                    "telefone": "11988887003",
                    "codigo": "000000",
                },
            )
            assert wrong.status_code == 400

        code = read_otp_code("11988887003")
        locked = await client.post(
            "/api/survey/verify-otp",
            json={"session_token": session_token, "telefone": "11988887003", "codigo": code},
        )
        # Mesmo com o código certo, a 6a tentativa já deve estar bloqueada
        # (a rota usa 400 para esse caso, não 429 — ver otp_service.py).
        assert locked.status_code == 400
        assert "máximo de tentativas" in locked.json()["detail"].lower()

    async def test_verify_without_prior_register_fails(self, client):
        res = await client.post(
            "/api/survey/verify-otp",
            json={
                "session_token": "token-que-nao-existe",
                "telefone": "11900000000",
                "codigo": "123456",
            },
        )
        assert res.status_code == 400
