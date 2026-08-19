# Testes automatizados

114 testes, três camadas: `tests/unit/`, `tests/integration/`, `tests/security/`.

## Rodando localmente

```bash
# 1. Infra de teste (banco e Redis dedicados — nunca aponta pra dados reais)
docker compose up -d db redis   # ou suba manualmente um Postgres/Redis locais

# criar o banco de teste, se ainda não existir:
psql -c "CREATE USER sondagemtest WITH PASSWORD 'sondagemtest' SUPERUSER;"
psql -c "CREATE DATABASE sondagem_test OWNER sondagemtest;"

# 2. Dependências de teste
pip install -r requirements-dev.txt

# 3. Rodar
pytest                          # tudo
pytest tests/unit/              # só unitários (rápidos, sem infra)
pytest tests/security/          # só as regressões de segurança
pytest --cov=app                # com cobertura (ver ressalva abaixo)
```

## Como a suíte funciona

- **`tests/unit/`** — funções puras (validação de CPF/telefone, geração de
  OTP, sanitização, hash de senha, JWT). Não tocam banco nem rede.

- **`tests/integration/`** — batem via HTTP real contra um servidor
  `uvicorn` de verdade, subido como subprocesso pela fixture
  `_live_server` (`tests/conftest.py`), não via `ASGITransport` in-process.
  Isso foi uma escolha deliberada: `BaseHTTPMiddleware`
  (`SecurityHeadersMiddleware`) combinado com conexões asyncpg presas ao
  loop de eventos que as abriu causa `Future ... attached to a different
  loop` quando testado in-process no mesmo loop do test runner. Um
  servidor de verdade não tem essa ambiguidade — e é também mais fiel ao
  comportamento real em produção.

- **`tests/security/`** — testes de regressão para os achados C1
  (XSS armazenado), C2 (bypass hardcoded do reCAPTCHA) e C3 (OTP em texto
  puro no Redis) da auditoria, mais o rate limit do login admin (A3). Cada
  um bate direto na causa raiz do bug original, não só no sintoma — se
  algum desses bugs voltar (ex: alguém reintroduzir `Form(...)` direto na
  rota de candidato em vez do schema sanitizado), o teste correspondente
  falha.

  Cobrem também as defesas adicionadas depois: headers de segurança e CSP
  (`test_security_headers.py`), confusão de algoritmo no JWT
  (`test_jwt_algorithm_confusion.py`) e a sessão do admin em cookie
  httpOnly com CSRF (`test_admin_cookie_auth.py`). Os três existem porque
  a falha correspondente é **silenciosa**: um middleware que pare de
  rodar, um `alg: none` aceito ou um cookie sem `httpOnly` não quebram
  nenhum teste de status — a aplicação segue respondendo 200.

## Por que o banco/Redis usam engines próprios por fixture

Cada fixture que toca o banco (`_schema`, `_clean_database`, `db_session`)
cria e descarta seu próprio `AsyncEngine` (com `NullPool`) inteiramente
dentro de si mesma, em vez de importar o `engine` compartilhado de
`app.database.session`. Reutilizar esse singleton entre fixtures de
escopos diferentes causava o mesmo erro de "loop diferente" mencionado
acima — cada fixture agora é autocontida e não depende de qual loop o
pytest-asyncio atribuiu a ela.

## Limitação conhecida: cobertura via `--cov`

Como os testes de integração batem num servidor rodando em **processo
separado**, o `coverage.py` do processo de teste não enxerga o código
executado dentro do servidor — rotas, schemas e repositories aparecem
como 0% cobertos no relatório mesmo sendo exercitados por dezenas de
asserções HTTP. Tentei contornar isso rodando o servidor sob
`coverage run --parallel-mode`, mas os dados não são persistidos mesmo em
um shutdown limpo (parece ser uma fricção conhecida entre coverage.py e
o encerramento de um processo asyncio/uvicorn) — não persegui mais a
fundo por não valer o tempo frente ao ganho.

**Na prática**: os 114 testes passando (incluindo os de regressão de
segurança batendo na API real) são o sinal confiável de cobertura
funcional — o número percentual do `--cov` para `app/api`, `app/schemas`
e `app/repositories` deve ser ignorado.

**Com uma ressalva que custou caro:** "todos passando" cobre só o que a
suíte exercita. O upgrade de starlette deixou `/` e `/admin` devolvendo
500 com 71 testes verdes, porque nenhum deles requisitava as páginas HTML.
Ao adicionar comportamento, pergunte o que continuaria verde se ele
quebrasse.

## Adicionando testes novos

- Teste unitário: função pura, sem `client`/`db_session` → `tests/unit/`
- Teste que bate na API: precisa da fixture `client` → `tests/integration/`
- Teste que existe especificamente para não deixar um bug de segurança
  voltar → `tests/security/`, com comentário explicando qual achado da
  auditoria ele cobre
