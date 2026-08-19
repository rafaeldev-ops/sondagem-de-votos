class TestOtpNeverStoredInPlaintext:
    """
    Regressão do achado C3 da auditoria: app/services/otp_service.py gravava
    `data["codigo"] = code` sem hash — qualquer acesso de leitura ao Redis
    (backup, réplica, porta exposta por engano) revelava o código ativo.
    Corrigido: só o hash SHA-256 é gravado (`codigo_hash`).

    Este teste lê o Redis diretamente após um /register e garante que o
    código em claro nunca aparece na chave.
    """

    async def test_redis_key_never_contains_plaintext_code(
        self, client, valid_cpf, numero_socio, read_otp_code
    ):
        from app.services.otp_service import RedisService

        telefone = "11966660001"
        await client.post(
            "/api/survey/register",
            json={
                "nome": "Teste Redis",
                "cpf": valid_cpf(),
                "telefone": telefone,
                "numero_socio": numero_socio(),
                "titular": True,
                "recaptcha_token": "",
            },
        )

        code = read_otp_code(telefone)

        rs = RedisService()
        redis_client = await rs.get_client()
        raw = await redis_client.get(f"otp:{telefone}")
        await rs.close()

        assert raw is not None
        assert code not in raw
        assert "codigo_hash" in raw
        assert '"codigo":' not in raw
