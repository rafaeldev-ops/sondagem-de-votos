import pytest


class TestAdminLogin:
    async def test_login_with_correct_credentials(self, client):
        res = await client.post(
            "/api/admin/login", json={"username": "admin", "password": "admin123"}
        )
        assert res.status_code == 200
        assert "access_token" in res.json()

    async def test_login_with_wrong_password(self, client):
        res = await client.post(
            "/api/admin/login", json={"username": "admin", "password": "senhaerrada"}
        )
        assert res.status_code == 401

    async def test_admin_route_requires_token(self, client):
        res = await client.get("/api/admin/stats")
        assert res.status_code in (401, 403)

    async def test_admin_route_rejects_invalid_token(self, client):
        res = await client.get(
            "/api/admin/stats", headers={"Authorization": "Bearer token-invalido"}
        )
        assert res.status_code == 401

    async def test_admin_route_accepts_valid_token(self, client, admin_token):
        res = await client.get(
            "/api/admin/stats", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert res.status_code == 200


class TestRotasDeWebhookForamRemovidas:
    """O envio por webhook saiu do projeto (migration 008): as exportações
    já entregavam tudo o que o payload levava. Nenhuma das duas grafias
    históricas da rota pode voltar a responder — se alguma voltar, é sinal
    de que a remoção foi revertida pela metade."""

    @pytest.mark.parametrize(
        "rota", ["/api/admin/webhook/retry", "/api/admin/pipefy/retry"]
    )
    async def test_rota_nao_existe_mais(self, client, admin_token, rota):
        res = await client.post(rota, headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 404
