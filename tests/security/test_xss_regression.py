class TestCandidatoXssRegression:
    """
    Regressão do achado C1 da auditoria: as rotas de candidato usavam
    Form(...) direto, ignorando os schemas Pydantic (CandidatoCreate/Update)
    que aplicariam sanitização — nome/apelido eram gravados sem limpeza e
    depois injetados via innerHTML sem escapar, tanto na página pública
    quanto no painel admin. Corrigido sanitizando na camada de serviço
    (app/services/admin_service.py). Este teste bate na API de verdade para
    garantir que a correção continua valendo mesmo se alguém re-escrever a
    rota no futuro.
    """

    async def test_xss_payload_in_nome_is_sanitized(self, client, admin_token):
        res = await client.post(
            "/api/admin/candidatos",
            headers={"Authorization": f"Bearer {admin_token}"},
            data={
                "nome": "<img src=x onerror=alert(1)>Fulano",
                "apelido": "Apelido normal",
                "ativo": "true",
            },
        )
        assert res.status_code in (200, 201)

        listing = await client.get(
            "/api/admin/candidatos", headers={"Authorization": f"Bearer {admin_token}"}
        )
        candidatos = listing.json()
        criado = next(c for c in candidatos if "Fulano" in c["nome"])
        assert "<img" not in criado["nome"]
        assert "onerror" not in criado["nome"]

    async def test_xss_payload_in_apelido_is_sanitized(self, client, admin_token):
        res = await client.post(
            "/api/admin/candidatos",
            headers={"Authorization": f"Bearer {admin_token}"},
            data={
                "nome": "Nome Normal",
                "apelido": "<script>alert(2)</script>Apelido",
                "ativo": "true",
            },
        )
        assert res.status_code in (200, 201)

        listing = await client.get(
            "/api/admin/candidatos", headers={"Authorization": f"Bearer {admin_token}"}
        )
        candidatos = listing.json()
        criado = next(c for c in candidatos if c["nome"] == "Nome Normal")
        assert "<script>" not in criado["apelido"]

    async def test_xss_payload_on_update_is_sanitized(self, client, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}

        create = await client.post(
            "/api/admin/candidatos",
            headers=headers,
            data={"nome": "Original", "apelido": "Original", "ativo": "true"},
        )
        candidato_id = create.json()["id"]

        await client.put(
            f"/api/admin/candidatos/{candidato_id}",
            headers=headers,
            data={"nome": "<svg onload=alert(3)>Editado"},
        )

        listing = await client.get("/api/admin/candidatos", headers=headers)
        atualizado = next(c for c in listing.json() if c["id"] == candidato_id)
        assert "<svg" not in atualizado["nome"]
        assert "onload" not in atualizado["nome"]
