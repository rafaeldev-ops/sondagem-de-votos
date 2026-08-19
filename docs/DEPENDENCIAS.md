# Auditoria de dependências

Status em 04/08/2026. Ferramenta: `pip-audit -r requirements.txt`
(instalada via `requirements-dev.txt`).

## Situação atual

**De 23 CVEs conhecidas para 0.**

```
$ pip-audit -r requirements.txt
No known vulnerabilities found
```

Todas as mudanças abaixo foram aplicadas com a suíte de testes rodando
entre cada uma — nenhuma quebrou nada (com uma ressalva importante sobre o
upgrade do starlette, registrada na seção dele).

### Já atualizadas ✅

| Pacote | De | Para | CVEs resolvidas |
|---|---|---|---|
| `python-jose` → `PyJWT` | 3.4.0 | 2.13.0 | 5 (elimina `ecdsa` e `pyasn1` da árvore) |
| `fastapi` + `starlette` | 0.115.6 / 0.41.3 | 0.141.1 / 1.3.1 | 7 (ver abaixo) |
| `python-jose[cryptography]` | 3.3.0 | 3.4.0 | 2 (validação de JWT do admin — era a mais crítica) |
| `python-multipart` | 0.0.20 | 0.0.31 | 6 (processa upload de foto de candidato) |
| `jinja2` | 3.1.4 | 3.1.6 | 3 |
| `bleach` | 6.2.0 | 6.4.0 | 2 (é a lib que faz a sanitização anti-XSS) |
| `python-dotenv` | 1.0.1 | 1.2.2 | 1 |

Além dessas, em rodadas anteriores:
- `bcrypt` fixado em 4.0.1 — `passlib` 1.7.4 quebra completamente com
  bcrypt ≥ 4.1 (reproduzido: `pwd_context.hash()` levantava exceção, o
  login admin não funcionava em instalação limpa)
- `twilio` 9.4.0 → 9.4.1 — a 9.4.0 é uma release *yanked* no PyPI

### `starlette` 0.41.3 → 1.3.1 + `fastapi` 0.115.6 → 0.141.1 (7 CVEs) ✅

Feito. Subiram juntos, como previsto — `starlette` é dependência direta do
FastAPI e subir sozinho quebra a resolução. O salto foi maior do que o
estimado (`starlette` cruzou a 1.0), mas **nada quebrou**: 64/64 testes
verdes na primeira tentativa, sem nenhuma alteração de código de
aplicação.

`starlette` agora está pinado **explicitamente** em `requirements.txt`,
mesmo sendo transitivo: era ele quem carregava as 7 CVEs, e deixá-lo
visível evita que a versão mude em silêncio junto com um upgrade futuro do
`fastapi`.

Sobre os pontos de atenção que estavam listados aqui antes:

- **`BaseHTTPMiddleware`** (`SecurityHeadersMiddleware`,
  `RequestIdMiddleware`) — era o risco principal e não se materializou.
  Verificado header a header nas duas versões: CSP, `X-Frame-Options`,
  `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`,
  `Cache-Control: no-store` nas rotas admin, `X-Request-ID` gerado e
  `X-Request-ID` reaproveitado do cliente — saída idêntica antes e depois.
- **`app.add_exception_handler`** — sem problema com a tipagem atual.
- **`TestClient`/lifespan** — não se aplica, a suíte não usa `TestClient`.

Lacuna encontrada no caminho: **nenhum teste afirmava nada sobre os
headers**. Um `BaseHTTPMiddleware` que parasse de rodar não quebraria a
suíte — a API responde 200 normalmente, só sem CSP e sem `X-Request-ID`.
Coberto agora por `tests/security/test_security_headers.py`.

### `python-jose` → `PyJWT` (5 CVEs: `ecdsa` x1, `pyasn1` x4) ✅

Feito. Essas 5 estavam presas: a `ecdsa` **não tem versão corrigida
publicada** (PYSEC-2026-1325, canal lateral de timing em curva elíptica) e
o `pyasn1` só corrige a partir da 0.6.3, enquanto o `python-jose` 3.4.0
exigia `pyasn1<0.5.0` — o pip acusava conflito explícito ao tentar fixar a
0.6.4. Não havia como resolvê-las sem sair do `python-jose`.

A troca eliminou **três** pacotes da árvore de dependências: `python-jose`,
`ecdsa` e `pyasn1` (e `cryptography`, que vinha pelo extra
`[cryptography]` e não é usada diretamente por nenhum código do projeto).

Mudou só `app/core/security.py`, como previsto:

```python
from jose import JWTError, jwt      ->  import jwt
                                        from jwt import PyJWTError
except JWTError:                     ->  except PyJWTError:
```

A assinatura de `create_access_token` / `decode_access_token` não mudou, e
nenhum call site (`app/api/deps.py`, `app/api/routes/admin.py`) foi
tocado. `tests/unit/test_security.py` passou **sem alteração nenhuma**.

Como a troca mexe em autenticação, ganhou cobertura extra em
`tests/security/test_jwt_algorithm_confusion.py`: `alg: none` (e a
variante `NONE`), token assinado em HS512 em vez de HS256, assinatura com
outro segredo, payload trocado sem reassinar e token sem assinatura. Todos
devem devolver `None`. Nenhum teste de roundtrip pega esse tipo de falha —
o caminho feliz continua funcionando enquanto o bypass está aberto.

Um dos testes afirma que `python-jose` **não** está mais instalável no
ambiente: se alguém reintroduzir a lib, `ecdsa` e `pyasn1` voltam junto e
as 5 CVEs com elas.

**Detalhe de operação:** o PyJWT 2.13 emite `InsecureKeyLengthWarning`
quando a chave HMAC tem menos de 32 bytes para HS256. A `SECRET_KEY` de
produção vem de `secrets.token_urlsafe(64)` (~86 caracteres), bem acima do
mínimo — mas se aparecer esse aviso no log, a `SECRET_KEY` é curta demais
e precisa ser trocada.

## Pendentes ⚠️

Nenhuma. `pip-audit -r requirements.txt` está limpo.

Dois pins que **não** devem ser mexidos sem cuidado:

- **`bcrypt==4.0.1`** — o `passlib` 1.7.4 quebra completamente com bcrypt
  ≥ 4.1 (`pwd_context.hash()` levanta exceção e o login admin para de
  funcionar em instalação limpa). Só sobe junto com a troca do passlib.
- **`starlette==1.3.1`** — pinado explicitamente mesmo sendo transitivo do
  `fastapi`, para não mudar em silêncio.

## Como reproduzir esta auditoria

```bash
pip install -r requirements-dev.txt
pip-audit -r requirements.txt
```

Roda também no CI (`.github/workflows/ci.yml`, job `test`) como etapa
informativa — reporta sem quebrar o pipeline. Esse modo informativo existia
porque CVEs sem correção disponível (como era o caso da `ecdsa`) travariam
todo deploy sem que houvesse ação possível. **Isso não é mais verdade:**
como o relatório está zerado, dá para tornar o `pip-audit` bloqueante no
CI — vale considerar, para que uma CVE nova apareça como falha de pipeline
em vez de uma linha de log que ninguém lê.
