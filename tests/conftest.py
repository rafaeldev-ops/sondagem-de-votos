"""
Configuração compartilhada dos testes.

IMPORTANTE: as variáveis de ambiente abaixo precisam ser definidas antes de
qualquer import de `app.*` — Settings() é lido no import de
app.database.session (via get_settings()), então se algum módulo de app
for importado antes deste bloco rodar, os testes vão usar a configuração
errada (ou vão falhar por falta de SECRET_KEY etc). Por isso esse bloco de
os.environ fica no topo do arquivo, antes de qualquer "from app import".

O banco e o Redis de teste são serviços separados dos de desenvolvimento
(mesma instância Postgres, banco "sondagem_test" dedicado; mesma instância
Redis, índice de banco 1 em vez de 0) — nunca aponta para dados reais.
"""

import os

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use-only")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://sondagemtest:sondagemtest@localhost:5432/sondagem_test",
)
os.environ.setdefault(
    "DATABASE_URL_SYNC",
    "postgresql+psycopg2://sondagemtest:sondagemtest@localhost:5432/sondagem_test",
)
os.environ.setdefault("REDIS_URL", "redis://:testpass123@localhost:6379/1")
os.environ.setdefault("REDIS_PASSWORD", "testpass123")
os.environ.setdefault("OTP_PROVIDER", "mock")
os.environ.setdefault("OTP_EXPIRY_SECONDS", "300")
os.environ.setdefault("OTP_MAX_ATTEMPTS", "5")
os.environ.setdefault("OTP_RESEND_COOLDOWN_SECONDS", "60")
os.environ.setdefault("RECAPTCHA_SECRET_KEY", "")
os.environ.setdefault("RECAPTCHA_SITE_KEY", "")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")
os.environ.setdefault("RATE_LIMIT_DEFAULT", "1000/minute")
os.environ.setdefault("RATE_LIMIT_OTP", "1000/minute")
# Também afrouxado, pelo mesmo motivo dos dois acima: o rate limit é por IP
# e todos os testes batem do mesmo 127.0.0.1 dentro da mesma janela de 1
# minuto. O default de produção (10/minute) comporta os testes que existiam
# antes de tests/integration/test_numero_socio.py, mas essa suíte sozinha já
# soma 6 chamadas a /register — somado ao resto, estoura o limite e derruba
# testes que nada têm a ver com rate limit (viram 429 em vez de 200).
# test_limites_do_fluxo_publico_batem_com_a_configuracao (em
# tests/security/test_rate_limits.py) lê esse valor de volta em vez de
# comparar com um número fixo, então continua válido com qualquer valor aqui.
os.environ.setdefault("RATE_LIMIT_REGISTER", "1000/minute")
# Mesmo motivo e mesma proteção de test_limites_do_fluxo_publico_batem_com_a_
# configuracao: /verify-otp (default de produção 15/minute) e /submit
# (default 10/minute) também são chamados várias vezes por teste em vários
# arquivos, na mesma janela compartilhada por IP. Sem isso, adicionar mais um
# teste de fluxo completo em qualquer arquivo pode empurrar a contagem total
# da suíte para além do limite de produção e derrubar testes que não têm
# nada a ver com rate limit.
os.environ.setdefault("RATE_LIMIT_VERIFY_OTP", "1000/minute")
os.environ.setdefault("RATE_LIMIT_SUBMIT", "1000/minute")
# Deliberadamente baixo, ao contrário dos outros: tests/security/
# test_rate_limits.py precisa que o limite seja realmente atingido.
#
# O valor precisa caber, na mesma janela de 1 minuto, todos os logins
# legítimos da suíte — 4 hoje: os dois de test_admin_auth.py e as fixtures
# de sessão admin_token e login_response (ambas de sessão exatamente para
# não gastar essa janela). Daí não poder ser menor que 4.
#
# É também diferente do default de produção (5/minute) de propósito: se
# alguém voltar a hardcodar o limite na rota, o valor registrado deixa de
# bater com este e TestRateLimitVemDeSettings falha.
os.environ.setdefault("RATE_LIMIT_ADMIN_LOGIN", "6/minute")
os.environ.setdefault("ALLOWED_ORIGINS", "http://testserver")
os.environ.setdefault("TRUST_PROXY_HEADERS", "false")
os.environ.setdefault("HTTPS_ONLY", "false")
os.environ.setdefault("UPLOAD_DIR", "uploads/candidatos")
os.environ.setdefault("MAX_UPLOAD_SIZE_MB", "5")

import itertools
import re
import socket
import subprocess
import sys
import tempfile
import time

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.database.base import Base

# Import necessário para popular Base.metadata com as tabelas antes de
# create_all — sem isso, Base.metadata fica vazio neste processo (o
# processo de teste nunca importa app.main, que é quem transitivamente
# importaria app.models via as rotas/repositories no processo do servidor).
import app.models  # noqa: F401,E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _schema():
    """
    Cria o schema uma vez por sessão de testes, via metadata (não Alembic —
    ver docs/TESTES.md sobre a troca deliberada de velocidade por fidelidade,
    e a suíte separada que valida as migrations de verdade).

    Usa um engine próprio, criado e descartado inteiramente dentro desta
    fixture (NullPool: nunca reaproveita conexão entre checkouts) — nunca o
    `engine` de app.database.session. Esse módulo é importado pelo processo
    do servidor de teste (ver _live_server) num loop de eventos diferente do
    processo de teste; reaproveitar o mesmo objeto Engine entre os dois
    causava "Future ... attached to a different loop" no meio da suíte.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    yield

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="session")
def _live_server():
    """
    Sobe a aplicação real (uvicorn, processo separado) para os testes de
    integração baterem via HTTP de verdade, em vez de ASGITransport
    in-process — mais fiel ao comportamento real em produção (rede de
    verdade, não atalho ASGI in-process) e evita qualquer ambiguidade de
    loop de eventos entre o cliente de teste e o app.

    Efeito colateral dessa escolha: o app roda em processo separado, então
    monkeypatch não alcança o provider de OTP mock de dentro dos testes — por
    isso a saída do servidor vai para um arquivo de log (ver read_otp_code
    abaixo), em vez de capturarmos o código via patch.
    """
    port = _free_port()
    env = os.environ.copy()
    env["PORT"] = str(port)

    log_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", prefix="uvicorn-test-", delete=False
    )

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 15
    last_error = None
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{base_url}/health", timeout=1)
            if resp.status_code == 200:
                break
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.3)
    else:
        proc.terminate()
        raise RuntimeError(f"Servidor de teste não respondeu a tempo: {last_error}")

    yield base_url, log_file.name

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    log_file.close()


@pytest_asyncio.fixture(autouse=True)
async def _clean_database():
    """Limpa as tabelas antes de cada teste, preservando o schema. Engine
    próprio da fixture, mesmo motivo do comentário em _schema."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
        await conn.commit()
    await engine.dispose()
    yield


@pytest_asyncio.fixture(autouse=True)
async def _clean_redis():
    """Limpa o Redis (índice de banco de teste) antes e depois de cada teste."""
    from app.services.otp_service import RedisService

    rs = RedisService()
    client = await rs.get_client()
    await client.flushdb()
    yield
    await client.flushdb()
    await rs.close()


@pytest_asyncio.fixture
async def client(_live_server):
    """Cliente HTTP assíncrono contra o servidor real de teste (rede local,
    não in-process) — ver _live_server acima para o motivo da escolha."""
    base_url, _ = _live_server
    async with httpx.AsyncClient(base_url=base_url, timeout=10) as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    """Sessão para o teste inspecionar/preparar dados diretamente no banco.
    Engine próprio da fixture, mesmo motivo do comentário em _schema."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def read_otp_code(_live_server):
    """Lê no log do servidor de teste o último código OTP enviado (provider
    mock) para um telefone dado. Faz pequenas re-tentativas porque a escrita
    no arquivo de log pelo processo do servidor não é instantânea em relação
    ao retorno da chamada HTTP que a disparou."""
    _, log_path = _live_server

    def _read(phone: str, attempts: int = 20, delay: float = 0.1) -> str:
        pattern = re.compile(rf"OTP mock enviado para {re.escape(phone)}: (\d+)")
        for _ in range(attempts):
            with open(log_path, encoding="utf-8", errors="ignore") as f:
                matches = pattern.findall(f.read())
            if matches:
                return matches[-1]
            time.sleep(delay)
        raise AssertionError(f"Código OTP para {phone} não encontrado no log do servidor")

    return _read


@pytest.fixture
def valid_cpf():
    """Gera um CPF matematicamente válido (dígitos verificadores corretos),
    determinístico o suficiente para não colidir entre testes na mesma run."""
    import random

    def calc(base: list[int]) -> int:
        weight = len(base) + 1
        total = sum(d * (weight - i) for i, d in enumerate(base))
        rest = total % 11
        return 0 if rest < 2 else 11 - rest

    def generate() -> str:
        base = [random.randint(0, 9) for _ in range(9)]
        d1 = calc(base)
        d2 = calc(base + [d1])
        return "".join(map(str, base)) + str(d1) + str(d2)

    return generate


@pytest.fixture
def numero_socio():
    """
    Gera números de sócio de 4 dígitos sequenciais (0001, 0002, ...), únicos
    dentro de UM teste. A fixture é function-scoped, então o contador
    reinicia do 1 a cada teste — não é ela quem garante números distintos
    ENTRE testes, isso é a fixture autouse `_clean_database`, que limpa a
    tabela antes de cada teste. O sequencial (em vez de random) evita só a
    colisão entre duas chamadas dentro do MESMO teste, que quebraria a
    constraint UNIQUE de forma intermitente. O `% 10000` existe para nunca
    gerar mais de 4 dígitos; na prática nenhum teste chama a fixture perto
    de 10.000 vezes, então esse teto não é alcançado.
    """
    contador = itertools.count(1)

    def generate() -> str:
        return f"{next(contador) % 10000:04d}"

    return generate


@pytest_asyncio.fixture
async def departamentos(db_session):
    """
    Cria departamentos para o teste. O seed real vive na migration 006, que
    a suíte não roda (o schema vem de create_all) — então cada teste que
    precisa de modalidades cria as suas.

    Devolve os objetos já com id, na ordem em que foram criados; quando
    com_outros=True o último é a opção que exige texto complementar.
    """

    async def create(quantos: int = 3, com_outros: bool = True):
        from app.models import Departamento

        criados = [
            Departamento(nome=f"Modalidade {i}", ordem=i, ativo=True)
            for i in range(1, quantos + 1)
        ]
        if com_outros:
            criados.append(
                Departamento(nome="Outros", ordem=999, exige_texto=True, ativo=True)
            )

        db_session.add_all(criados)
        await db_session.commit()
        for d in criados:
            await db_session.refresh(d)
        return criados

    return create


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def admin_token(_live_server):
    """
    Token de admin único, obtido uma vez por sessão de testes e reutilizado
    por qualquer teste que só precise "ter um token válido" (não estar
    testando o login em si). O login tem rate limit de 5/minuto (correto,
    ver A3 no relatório de auditoria) — chamar /api/admin/login em cada
    teste que precisa de um token estourava esse limite legítimo assim que
    a suíte crescia. Testes que testam o LOGIN em si (sucesso, falha,
    rate limit) continuam chamando a rota diretamente, não usam esta
    fixture.
    """
    base_url, _ = _live_server
    async with httpx.AsyncClient(base_url=base_url, timeout=10) as ac:
        res = await ac.post(
            "/api/admin/login", json={"username": "admin", "password": "admin123"}
        )
        assert res.status_code == 200, f"setup: login falhou: {res.status_code} {res.text}"
        return res.json()["access_token"]
