"""Seed sample candidates for development.

Usage:
    python -m scripts.seed_candidatos      (a partir da raiz do projeto)

Rode como módulo (-m), não por caminho. `python scripts/seed_candidatos.py`
coloca `scripts/` em sys.path[0] em vez da raiz do projeto, e o import de
`app` abaixo falha com ModuleNotFoundError. O `-m` mantém o diretório
atual em sys.path, que é onde `app/` está.

Note que `scripts/hash_password.py` roda pelas duas formas — ele não
importa nada de `app`, só de passlib. Por isso a documentação usa `-m` só
aqui.
"""

import asyncio

from app.database.session import AsyncSessionLocal
from app.models import Candidato


async def seed() -> None:
    candidatos = [
        Candidato(nome="Maria Santos", apelido="Mari", ativo=True),
        Candidato(nome="Pedro Oliveira", apelido="Pedro", ativo=True),
        Candidato(nome="Ana Costa", apelido="Aninha", ativo=True),
        Candidato(nome="Carlos Mendes", apelido="Carlão", ativo=True),
    ]

    async with AsyncSessionLocal() as db:
        db.add_all(candidatos)
        await db.commit()
        print(f"{len(candidatos)} candidatos criados.")


if __name__ == "__main__":
    asyncio.run(seed())
