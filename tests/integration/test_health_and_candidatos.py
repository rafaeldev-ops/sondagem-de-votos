class TestHealth:
    async def test_health_returns_ok(self, client):
        res = await client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    async def test_readiness_checks_dependencies(self, client):
        res = await client.get("/health/ready")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ready"
        assert body["checks"]["database"] is True
        assert body["checks"]["redis"] is True


class TestCandidatos:
    async def test_list_empty_by_default(self, client):
        res = await client.get("/api/survey/candidatos")
        assert res.status_code == 200
        assert res.json() == []

    async def test_list_returns_seeded_candidatos(self, client, db_session):
        from app.models import Candidato

        db_session.add(Candidato(nome="Maria Santos", apelido="Mari", ativo=True))
        db_session.add(Candidato(nome="Inativo", apelido="Nao aparece", ativo=False))
        await db_session.commit()

        res = await client.get("/api/survey/candidatos")
        assert res.status_code == 200
        body = res.json()
        assert len(body) == 1
        assert body[0]["nome"] == "Maria Santos"

    async def test_list_ordena_por_apelido_alfabetico(self, client, db_session):
        """
        A ordem é pelo APELIDO, não pelo nome completo: "Zeca" (nome
        "Adriano Zeca") precisa vir depois de "Mari" mesmo com o nome
        começando com A — quem escolhe na tela 3 reconhece o candidato pelo
        apelido, não pelo nome civil.
        """
        from app.models import Candidato

        db_session.add(Candidato(nome="Adriano Silva", apelido="Zeca", ativo=True))
        db_session.add(Candidato(nome="Beatriz Souza", apelido="Bia", ativo=True))
        db_session.add(Candidato(nome="Carlos Lima", apelido="Mari", ativo=True))
        await db_session.commit()

        res = await client.get("/api/survey/candidatos")
        assert res.status_code == 200
        apelidos = [c["apelido"] for c in res.json()]
        assert apelidos == ["Bia", "Mari", "Zeca"]
