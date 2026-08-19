"""
Exportação do resultado consolidado: uma linha por pré-candidato, sem
identificador pessoal nenhum.

Existe para quem só precisa do RESULTADO da sondagem. O aviso de privacidade
do formulário promete uso restrito a validação de segurança e prevenção de
duplicidade, então entregar CPF e telefone junto de uma contagem de votos é
mais do que foi combinado com o sócio. Estes testes vigiam as duas
propriedades que fazem esse arquivo servir a esse fim: os números batem, e
nenhum dado pessoal vaza para dentro dele.
"""

import csv
import io

import pytest

from app.models import Candidato


# Recebe o id da modalidade pronto em vez de criá-la: `departamentos` tem
# UNIQUE em nome e gera sempre "Modalidade 1", então chamar a fixture uma vez
# por voto estoura a constraint no segundo votante do mesmo teste.
async def _votar(
    client, db_session, valid_cpf, numero_socio, read_otp_code, departamento_id,
    telefone, candidatos_ids, preferido_id,
):
    res = await client.post(
        "/api/survey/register",
        json={
            "nome": "Socio Resultado",
            "cpf": valid_cpf(),
            "telefone": telefone,
            "numero_socio": numero_socio(),
            "titular": True,
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
            "candidatos_ids": candidatos_ids,
            "candidato_preferido_id": preferido_id,
            "departamentos_ids": [departamento_id],
            "aceite_lgpd": True,
        },
    )
    assert res.status_code == 200, res.text


async def _baixar_csv(client, admin_token):
    res = await client.get(
        "/api/admin/export/resultados/csv",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    return list(csv.reader(io.StringIO(res.text)))


class TestContagem:
    async def test_soma_votos_e_ponto_focal_por_candidato(
        self, client, db_session, valid_cpf, numero_socio, read_otp_code,
        departamentos, admin_token,
    ):
        """Dois sócios votam. Ambos marcam o candidato A; só um marca o B.
        O ponto focal do primeiro é A, o do segundo é B."""
        a = Candidato(nome="Ana Lima", apelido="Ana", ativo=True)
        b = Candidato(nome="Bruno Sá", apelido="Bruno", ativo=True)
        db_session.add_all([a, b])
        await db_session.commit()
        await db_session.refresh(a)
        await db_session.refresh(b)
        dep = (await departamentos(quantos=1, com_outros=False))[0]

        await _votar(
            client, db_session, valid_cpf, numero_socio, read_otp_code,
            dep.id, "11944440001", [a.id], a.id,
        )
        await _votar(
            client, db_session, valid_cpf, numero_socio, read_otp_code,
            dep.id, "11944440002", [a.id, b.id], b.id,
        )

        linhas = await _baixar_csv(client, admin_token)
        cab = linhas[0]
        dados = {linha[0]: linha for linha in linhas[1:]}

        assert dados["Ana Lima"][cab.index("Votos")] == "2"
        assert dados["Ana Lima"][cab.index("Ponto Focal")] == "1"
        assert dados["Bruno Sá"][cab.index("Votos")] == "1"
        assert dados["Bruno Sá"][cab.index("Ponto Focal")] == "1"

        # 2 respondentes: A foi marcado pelos dois, B por um.
        assert dados["Ana Lima"][cab.index("% dos Respondentes")] == "100.0"
        assert dados["Bruno Sá"][cab.index("% dos Respondentes")] == "50.0"

    async def test_ordena_do_mais_votado_para_o_menos(
        self, client, db_session, valid_cpf, numero_socio, read_otp_code,
        departamentos, admin_token,
    ):
        """Quem lidera precisa estar no topo — é a pergunta que o arquivo
        responde."""
        pouco = Candidato(nome="Aaa Pouco", apelido="Pouco", ativo=True)
        muito = Candidato(nome="Zzz Muito", apelido="Muito", ativo=True)
        db_session.add_all([pouco, muito])
        await db_session.commit()
        await db_session.refresh(pouco)
        await db_session.refresh(muito)
        dep = (await departamentos(quantos=1, com_outros=False))[0]

        await _votar(
            client, db_session, valid_cpf, numero_socio, read_otp_code,
            dep.id, "11944440003", [muito.id], muito.id,
        )

        linhas = await _baixar_csv(client, admin_token)
        # Ordem alfabética colocaria "Aaa Pouco" primeiro; a ordenação é por
        # voto, então quem tem 1 voto vem antes de quem tem 0.
        assert [linha[0] for linha in linhas[1:]] == ["Zzz Muito", "Aaa Pouco"]

    async def test_candidato_sem_voto_aparece_com_zero(
        self, client, db_session, admin_token
    ):
        """Sumir da lista e ter zero voto são coisas diferentes: quem lê o
        arquivo precisa ver que o candidato existia e não foi votado."""
        db_session.add(Candidato(nome="Sem Votos", apelido="Zero", ativo=True))
        await db_session.commit()

        linhas = await _baixar_csv(client, admin_token)
        cab = linhas[0]
        assert linhas[1][0] == "Sem Votos"
        assert linhas[1][cab.index("Votos")] == "0"

    async def test_sem_nenhuma_resposta_nao_estoura(
        self, client, db_session, admin_token
    ):
        """Divisão por zero: o relatório pode ser baixado antes do primeiro
        voto, e o percentual não tem denominador."""
        db_session.add(Candidato(nome="Ninguem Votou", apelido="NV", ativo=True))
        await db_session.commit()

        linhas = await _baixar_csv(client, admin_token)
        cab = linhas[0]
        assert linhas[1][cab.index("% dos Respondentes")] == "0.0"


class TestNaoVazaDadoPessoal:
    async def test_csv_nao_contem_cpf_nome_nem_telefone_de_socio(
        self, client, db_session, valid_cpf, numero_socio, read_otp_code,
        departamentos, admin_token,
    ):
        """A razão de existir do arquivo. Se um identificador pessoal
        aparecer aqui, ele deixa de ser o export seguro de compartilhar e
        vira uma cópia do outro."""
        candidato = Candidato(nome="Alvo", apelido="Alvo", ativo=True)
        db_session.add(candidato)
        await db_session.commit()
        await db_session.refresh(candidato)

        cpf = valid_cpf()
        telefone = "11944440009"
        res = await client.post(
            "/api/survey/register",
            json={
                "nome": "Fulano Identificavel",
                "cpf": cpf,
                "telefone": telefone,
                "numero_socio": "4242",
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
        deps = await departamentos(quantos=1, com_outros=False)
        await client.post(
            "/api/survey/submit",
            json={
                "session_token": token,
                "candidatos_ids": [candidato.id],
                "candidato_preferido_id": candidato.id,
                "departamentos_ids": [deps[0].id],
                "aceite_lgpd": True,
            },
        )

        res = await client.get(
            "/api/admin/export/resultados/csv",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        texto = res.text

        assert "Fulano Identificavel" not in texto
        assert cpf not in texto
        assert telefone not in texto
        assert "4242" not in texto
        # O que deve estar lá: o candidato e a contagem.
        assert "Alvo" in texto


class TestAcesso:
    @pytest.mark.parametrize(
        "rota",
        ["/api/admin/export/resultados/csv", "/api/admin/export/resultados/excel"],
    )
    async def test_exige_autenticacao(self, client, rota):
        """Agregado não é público: a sondagem está em andamento, e o placar
        parcial não deve vazar antes da hora."""
        assert (await client.get(rota)).status_code in (401, 403)

    async def test_excel_responde(self, client, db_session, admin_token):
        db_session.add(Candidato(nome="Excel", apelido="X", ativo=True))
        await db_session.commit()

        res = await client.get(
            "/api/admin/export/resultados/excel",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        assert "spreadsheetml" in res.headers["content-type"]
