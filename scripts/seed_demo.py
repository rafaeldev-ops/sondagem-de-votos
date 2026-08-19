"""Popula o banco com uma sondagem inteira de mentira, para demonstração.

Uso:
    python -m scripts.seed_demo      (a partir da raiz do projeto)

Rode como módulo (-m) pelo mesmo motivo de scripts/seed_candidatos.py:
chamar por caminho coloca scripts/ em sys.path[0] e o import de `app`
falha.

TODOS os dados aqui são inventados. Nenhum CPF, nome, telefone ou voto
corresponde a associado real do clube — é justamente esse o ponto: dá
para gravar a tela e tirar print do painel sem expor dado de ninguém.

O script é destrutivo e idempotente: apaga associados, candidatos e tudo
que pende deles antes de recriar. Ele SE RECUSA a rodar com DEBUG=false,
porque apontá-lo para o banco de produção apagaria a sondagem real.
"""

import asyncio
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.database.session import AsyncSessionLocal
from app.models import (
    Associado,
    AssociadoDepartamento,
    Candidato,
    Departamento,
    Preferencia,
    Resposta,
)

_FUSO = ZoneInfo("America/Sao_Paulo")

# --------------------------------------------------------------------------
# Candidatos fictícios da urna.
# --------------------------------------------------------------------------
CANDIDATOS = [
    ("Marcos Antônio Prado", "Marcão"),
    ("Helena Vasques Ribeiro", "Lena"),
    ("Otávio Bezerra Lima", "Tavinho"),
    ("Regina Nakamura", "Regina"),
    ("Cláudio Ferrari", "Claudinho"),
    ("Vera Lúcia Amorim", "Dona Vera"),
]

# --------------------------------------------------------------------------
# Associados que "responderam" a sondagem.
#
# Campos: nome, CPF, telefone, número de sócio, titular, candidatos votados
# (posição em CANDIDATOS, começando em 1), ponto focal, modalidades (coluna
# `ordem` da tabela departamentos), texto de "Outros", minutos atrás.
#
# Os votos são desiguais de propósito: distribuição uniforme deixa o
# resultado consolidado com todas as barras do mesmo tamanho, que é
# exatamente o print que não convence ninguém.
#
# Rafael dos Santos é o último da lista e tem o `data_resposta` mais
# recente. Como o repositório ordena por data decrescente, ele aparece no
# TOPO da busca do painel e da planilha exportada.
# --------------------------------------------------------------------------
ASSOCIADOS = [
    # nome, cpf, telefone, socio, titular, votos, focal, modalidades, outros, min
    ("Levi Henry Oliveira", "87522252083", "18999208867", "0104", True, [1, 2, 3], 1, [1, 20], None, 8640),
    ("Carlos Eduardo Julio", "34210504068", "83991352087", "0217", True, [1, 4], 4, [17, 39], None, 7905),
    ("Ricardo Sales", "43658126027", "11984327719", "0332", False, [2, 3, 5], 2, [1, 38, 40], None, 7220),
    ("Luana Isabel", "13466968020", "21996142205", "0418", True, [1], 1, [25, 36], None, 6480),
    ("Bianca Porto", "31551529076", "31988714063", "0526", False, [1, 2, 6], 2, [5, 47], None, 5755),
    ("Sebastião Anderson", "00889706042", "41992056834", "0641", True, [3, 4], 3, [9, 40], None, 4990),
    ("Severino Martins", "20548057001", "48983761592", "0759", True, [1, 2, 3, 5], 1, [2, 32], None, 4310),
    ("Manoel Juan Novaes", "47263915855", "51994473018", "0863", False, [2, 6], 2, [39], None, 3580),
    ("Filipe Lucas", "18530476271", "62981597264", "0972", True, [1, 3], 3, [28, 48], None, 2845),
    ("Bryan Silveira", "73985120404", "71997304851", "1085", False, [1, 4], 1, [1, 31], None, 2110),
    ("Enrico Miguel", "29641758373", "85986042937", "1194", True, [1, 2], 1, [999], "Xadrez", 1395),
    ("Ian Teixeira", "60492837104", "92993185476", "1207", True, [1, 5], 5, [27, 36, 38], None, 640),
    ("Rafael dos Santos", "63649453924", "11976526746", "1315", True, [1, 2, 3, 4], 1, [1, 20, 44], None, 12),
]


async def seed() -> None:
    settings = get_settings()
    if not settings.debug:
        print(
            "ERRO: seed_demo apaga TODOS os associados e candidatos do banco "
            "e só roda com DEBUG=true. Se você está apontando para o banco de "
            "produção, este script destruiria a sondagem real.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    agora = datetime.now(_FUSO)

    async with AsyncSessionLocal() as db:
        # Ordem obrigatória: as três primeiras têm FK para associados e/ou
        # candidatos, então apagar associados antes estouraria a constraint.
        for tabela in (AssociadoDepartamento, Preferencia, Resposta, Associado, Candidato):
            await db.execute(delete(tabela))

        candidatos = [
            Candidato(nome=nome, apelido=apelido, ativo=True)
            for nome, apelido in CANDIDATOS
        ]
        db.add_all(candidatos)
        # flush e não commit: precisamos dos ids gerados para as FKs abaixo,
        # mas o seed inteiro tem que ser uma transação só — se algo falhar no
        # meio, o banco não fica com meia sondagem dentro.
        await db.flush()

        # Modalidades vêm da migration 006, não deste script. Indexadas por
        # `ordem` (e não pelo nome) porque os nomes oficiais têm acento,
        # travessão U+2013 e grafias propositalmente irregulares — casar por
        # string aqui quebraria na primeira correção de acento lá.
        deps = (await db.execute(select(Departamento))).scalars().all()
        por_ordem = {d.ordem: d for d in deps}
        if not por_ordem:
            print(
                "ERRO: tabela departamentos vazia. Rode 'alembic upgrade head' "
                "antes do seed.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        total_votos = 0
        for nome, cpf, tel, socio, titular, votos, focal, mods, outros, minutos in ASSOCIADOS:
            associado = Associado(
                nome=nome,
                cpf=cpf,
                numero_socio=socio,
                telefone=tel,
                titular=titular,
                aceite_lgpd=True,
                departamento_outros=outros,
                # IP fixo de documentação (RFC 5737, TEST-NET-1): a coluna não
                # pode ficar vazia num print do painel, e um IP inventado
                # qualquer poderia ser de alguém.
                ip="192.0.2.10",
                user_agent="Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Mobile",
                data_resposta=agora - timedelta(minutes=minutos),
            )
            db.add(associado)
            await db.flush()

            db.add_all(
                Resposta(associado_id=associado.id, candidato_id=candidatos[i - 1].id)
                for i in votos
            )
            total_votos += len(votos)

            db.add(
                Preferencia(
                    associado_id=associado.id,
                    candidato_preferido_id=candidatos[focal - 1].id,
                )
            )

            db.add_all(
                AssociadoDepartamento(
                    associado_id=associado.id, departamento_id=por_ordem[o].id
                )
                for o in mods
                if o in por_ordem
            )

        await db.commit()

    print(f"{len(CANDIDATOS)} candidatos criados.")
    print(f"{len(ASSOCIADOS)} associados criados, {total_votos} votos no total.")
    print(f"Resposta mais recente: {ASSOCIADOS[-1][0]} (CPF {ASSOCIADOS[-1][1]}).")


if __name__ == "__main__":
    asyncio.run(seed())
