# Guia de Produção

Deploy, rollback, backup/restore e troubleshooting.

> **Imagem validada em 04/08/2026.** O `Dockerfile` e o
> `docker-compose.yml` foram escritos num ambiente sem Docker e nunca
> tinham sido executados de verdade. Foram agora — ver seção 10.

---

## 1. Pré-requisitos

Antes do primeiro deploy, tenha em mãos:

- [ ] Provedor de OTP contratado (Twilio, Zenvia ou Z-API) com credenciais
- [ ] Chaves do Google reCAPTCHA v3 (site key + secret key)
- [ ] Domínio com certificado TLS (HTTPS) — a aplicação trata CPF e
      telefone; HTTP puro não é aceitável
- [ ] Hash bcrypt da senha do admin (ver seção 2)

---

## 2. Variáveis de ambiente

Copie `.env.example` para `.env` e preencha. As que **não podem** ficar no
default:

| Variável | Como obter / valor esperado |
|---|---|
| `APP_ENV` | `production` |
| `DEBUG` | `false` — **nunca `true` em produção** (expõe `/api/docs` e desliga a verificação de reCAPTCHA) |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `POSTGRES_PASSWORD` | senha forte e única |
| `REDIS_PASSWORD` | senha forte e única |
| `ADMIN_PASSWORD` | **hash bcrypt**, não a senha: `python scripts/hash_password.py "sua-senha"` |
| `OTP_PROVIDER` | `twilio`, `zenvia` ou `zapi` — **nunca `mock`** |
| `RECAPTCHA_SECRET_KEY` | console do Google reCAPTCHA |
| `HTTPS_ONLY` | `true` (ativa HSTS) |
| `TRUST_PROXY_HEADERS` | `true` **somente** se houver proxy reverso confiável na frente — e obrigatoriamente `true` se houver, senão o rate limit por IP vira limite global do site |
| `ALLOWED_ORIGINS` | domínio real, ex: `https://sondagem.seuclube.com.br` |

A aplicação **recusa iniciar** se `ADMIN_PASSWORD` não for um hash bcrypt
fora de `APP_ENV=development` — isso é proposital (fail-fast).

---

## 3. Deploy

```bash
# 1. Backup ANTES de qualquer coisa (ver seção 5)
./scripts/backup.sh

# 2. Puxar a versão nova
git fetch --all
git checkout <tag-ou-commit>

# 3. Build e subida
docker compose build
docker compose up -d

# 4. Migrations (ver seção 4 — nunca pule o backup antes)
docker compose exec app alembic upgrade head

# 5. Verificação pós-deploy
curl -f https://seu-dominio/health          # liveness
curl -f https://seu-dominio/health/ready    # readiness: DB + Redis
# As páginas renderizadas NÃO são cobertas pelos dois acima — /health não
# toca template nenhum. Já houve uma regressão em que os dois respondiam
# 200 com as duas páginas devolvendo 500 (ver seção 10).
curl -f https://seu-dominio/                # fluxo público
curl -f https://seu-dominio/admin           # painel admin
```

**Checklist de verificação pós-deploy:**

- [ ] `/health` responde 200
- [ ] `/health/ready` responde 200 com `database: true` e `redis: true`
- [ ] `/` e `/admin` respondem 200 (não basta o `/health`)
- [ ] `/api/docs` responde **404** (confirma `DEBUG=false`)
- [ ] Página inicial carrega e lista os candidatos
- [ ] Um cadastro de teste recebe SMS de verdade
- [ ] Logs saem em JSON com `request_id` preenchido

---

## 4. Migrations com segurança

**Regra:** backup do banco antes de toda migration, sem exceção.

```bash
# 1. Backup
./scripts/backup.sh

# 2. Ver o que será aplicado, ANTES de aplicar
docker compose exec app alembic current      # revisão atual
docker compose exec app alembic history      # histórico
docker compose exec app alembic upgrade head --sql > /tmp/migration.sql
# revise /tmp/migration.sql — especialmente DROP/ALTER em coluna existente

# 3. Aplicar
docker compose exec app alembic upgrade head
```

### Se uma migration falhar

O Alembic roda cada migration em transação (Postgres tem DDL
transacional), então uma migration que falha no meio faz rollback sozinha
— o banco não fica em estado parcial. Passos:

```bash
docker compose exec app alembic current     # confirme onde parou
docker compose logs app | tail -50          # veja o erro real
# corrija a migration, ou volte uma revisão:
docker compose exec app alembic downgrade -1
```

Se mesmo assim o banco ficar inconsistente, restaure o backup (seção 5).

---

## 5. Backup e restore

### Backup

```bash
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip > backup-$(date +%Y%m%d-%H%M%S).sql.gz
```

Recomendações:
- Automatize via cron **diariamente** durante o período da sondagem
- Guarde fora da máquina de produção (S3, Backblaze, etc)
- Retenha ao menos 7 dias
- **Teste o restore pelo menos uma vez** — backup nunca testado não é
  backup

O Redis não precisa de backup: guarda apenas OTPs efêmeros e sessões. Se
perder tudo, no pior caso alguns usuários precisam pedir um código novo.

### Restore

```bash
docker compose stop app             # pare a aplicação primeiro
gunzip -c backup-XXXXX.sql.gz | docker compose exec -T db \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
docker compose start app
curl -f https://seu-dominio/health/ready
```

---

## 6. Rollback

### Rollback só de aplicação (sem mudança de schema)

Caso mais comum e mais simples:

```bash
git checkout <commit-anterior-que-funcionava>
docker compose build && docker compose up -d
curl -f https://seu-dominio/health/ready
```

### Rollback com migration envolvida

```bash
# 1. Voltar o schema PRIMEIRO (a versão antiga do código não conhece o
#    schema novo)
docker compose exec app alembic downgrade -1

# 2. Depois voltar o código
git checkout <commit-anterior>
docker compose build && docker compose up -d
```

Se o `downgrade` não existir ou falhar → restaure o backup (seção 5). É
por isso que o backup pré-migration não é opcional.

### Quando fazer rollback

Faça rollback se, após o deploy:

- `/health/ready` não fica verde em alguns minutos
- taxa de erro 5xx sobe visivelmente nos logs
- o fluxo de OTP para de funcionar (ninguém recebe código)

Rollback primeiro, investigação depois — não debugue com a sondagem no ar
quebrada.

---

## 7. Monitoramento

### Endpoints

| Endpoint | Uso |
|---|---|
| `GET /health` | Liveness — o processo está de pé? Use no healthcheck do Docker/orquestrador |
| `GET /health/ready` | Readiness — consegue falar com Postgres e Redis? Use no load balancer |

Distinção importante: uma instabilidade momentânea do banco deve tirar a
instância do balanceamento (readiness), **não** reiniciar o container
(liveness).

### Logs

Fora de `DEBUG`, os logs saem em JSON, uma linha por evento:

```json
{"timestamp":"...","level":"INFO","logger":"app.middlewares.request_id",
 "message":"POST /api/survey/register -> 200 (45.2ms)","request_id":"a1b2c3d4"}
```

O `request_id` correlaciona todas as linhas de uma mesma requisição. Se o
proxy reverso enviar `X-Request-ID`, esse valor é reaproveitado.

**O que vigiar:**

| Sinal | Significado |
|---|---|
| `OTP_PROVIDER=mock fora de modo debug` | **Grave** — configuração errada, nenhum SMS está saindo |
| `reCAPTCHA sem RECAPTCHA_SECRET_KEY` | Proteção anti-bot desligada |
| Muitos 429 | Ataque, ou rate limit apertado demais |
| Latência subindo | Ver `docs/TESTE_DE_CARGA.md` para os limites conhecidos |

Logs **nunca** contêm CPF completo, telefone completo, senha ou código
OTP. Se algum aparecer, é bug — reporte.

---

## 8. Troubleshooting

### Aplicação não sobe

```bash
docker compose logs app | tail -50
```

| Erro | Causa | Solução |
|---|---|---|
| `ADMIN_PASSWORD precisa ser um hash bcrypt` | senha em texto puro no `.env` | `python scripts/hash_password.py "senha"` |
| `defina POSTGRES_PASSWORD no .env` | variável faltando | preencha o `.env` |
| `Connection refused` porta 5432 | banco não subiu | `docker compose ps`, veja logs do `db` |
| `relation "..." does not exist` | migrations não aplicadas | `alembic upgrade head` |
| `PermissionError: [Errno 13] Permission denied: 'uploads/candidatos'` (container reinicia em loop) | `uploads/` pertence a quem clonou o repo, mas o container roda como uid 999 | `sudo chown -R 999:999 uploads` no host, depois `docker compose up -d --force-recreate app` |

### Ninguém recebe o código OTP

1. `OTP_PROVIDER` está como `mock`? Em produção tem que ser um provedor real.
2. Credenciais do provedor corretas? Veja `ERROR` nos logs no envio.
3. Saldo/cota do provedor acabou?
4. O número tem DDD e 9 dígitos? (`app/utils/phone.py` valida isso)

### Como entregar os dados a terceiros

Não há mais envio automático: a saída de dados é a exportação pelo painel
admin. São duas, e a escolha entre elas importa.

**Resultado consolidado** (`Resultado CSV` / `Resultado Excel`) — votos por
pré-candidato, sem nenhum identificador pessoal. É o arquivo a compartilhar
com quem só precisa saber quem lidera.

**Respostas completas** (`Exportar CSV` / `Exportar Excel`) — inclui nome,
CPF e telefone dos associados. O aviso de privacidade do formulário diz ao
sócio que os dados são usados "exclusivamente para validação de segurança e
prevenção contra duplicidade"; repassar este arquivo para fora vai além do
que foi informado. Alinhe com quem responde pelo clube antes, ou ajuste o
texto do aviso.

### Usuário diz que não consegue votar

| Mensagem | Causa |
|---|---|
| "Este CPF já participou" | Já votou — comportamento correto |
| "Aguarde X segundos" | Cooldown de reenvio |
| "Número máximo de tentativas" | Errou o código 5 vezes; precisa de código novo |
| "Código expirado" | Passou de 5 minutos |
| 429 | Rate limit — muitas tentativas do mesmo IP |

Para investigar um caso específico, peça o horário aproximado e busque nos
logs por `request_id` daquele período (o CPF não estará nos logs, por
design).

---

## 9. Segurança operacional

- Rotacione `SECRET_KEY` se suspeitar de vazamento — invalida todos os
  tokens de admin ativos
- Nunca commite `.env` (já está no `.gitignore`)
- **`HTTPS_ONLY=true` é obrigatório em produção.** Além do HSTS, é ele
  que liga a flag `Secure` nos cookies de sessão do admin — sem isso o
  cookie viaja em texto puro se alguém acessar o painel por `http://`
- Postgres e Redis não devem ter porta pública; no `docker-compose.yml`
  estão em `127.0.0.1` de propósito
- Revise `audit_logs` periodicamente
- Após a sondagem terminar, considere exportar os dados e **remover os
  CPFs do banco** — LGPD: não guarde dado pessoal além do necessário

---

## 10. Validação da imagem Docker

Executado em 04/08/2026 com Docker 29.6.2 / Compose v5.3.1. Até então o
`Dockerfile` e o `docker-compose.yml` nunca tinham rodado — foram escritos
num ambiente sem Docker.

**O build passou de primeira, sem nenhuma correção necessária.** O que foi
conferido:

| Verificação | Resultado |
|---|---|
| `docker compose build` (multi-stage com venv em `/opt/venv`) | ✅ |
| `docker compose up -d` — os 3 serviços sobem e ficam `healthy` | ✅ |
| `docker compose exec app alembic upgrade head` (001 e 002) | ✅ |
| `curl -f http://localhost:8000/health` | ✅ `{"status":"ok"}` |
| `curl -f http://localhost:8000/health/ready` | ✅ `database: true, redis: true` |
| `docker compose exec app whoami` | ✅ `app` (uid 999, **não** root) |
| `gcc` e headers do `libpq-dev` ausentes na imagem final | ✅ (ficaram no stage de build) |
| `uploads/` gravável pelo usuário `app` através do bind mount | ✅ |
| `/app` **não** gravável pelo usuário `app` | ✅ (só `uploads/` e `static/` têm `chown`) |
| Páginas `/` e `/admin`, estáticos e login admin | ✅ (depois da correção abaixo) |

Tamanho da imagem final: **426 MB**.

### O bug que só apareceu aqui

Subir a stack de verdade encontrou uma regressão que os 71 testes da suíte
não pegaram: `/` e `/admin` devolviam **HTTP 500**. Causa: o upgrade do
starlette mudou a assinatura de `TemplateResponse`, e nenhum teste
requisitava as páginas HTML — a suíte só batia em rotas de API e em
`/health`. Corrigido em `app/main.py`, com
`tests/integration/test_paginas_html.py` cobrindo o buraco.

Vale como lição operacional: **`/health` respondendo `200` não significa
que a aplicação está servindo**. O `HEALTHCHECK` do `docker-compose.yml`
só bate em `/health`, que é liveness puro e não toca template nenhum — um
container com as duas páginas quebradas continua marcado `healthy` e
passaria por um rolling deploy sem alarme algum. Foi o que aconteceu aqui:
o container ficou `healthy` com `/` e `/admin` em 500.

O checklist da seção 3 já pedia "página inicial carrega", mas era um item
manual, fácil de pular — os comandos `curl` prontos para copiar cobriam só
os dois `/health`. Agora incluem `/` e `/admin`.

### Reproduzir

```bash
cp .env.example .env    # preencha POSTGRES_USER/PASSWORD, REDIS_PASSWORD, SECRET_KEY
docker compose build
docker compose up -d
docker compose exec app alembic upgrade head
curl -f http://localhost:8000/health
curl -f http://localhost:8000/health/ready
curl -f http://localhost:8000/          # não pule este
curl -f http://localhost:8000/admin     # nem este
docker compose exec app whoami          # precisa responder "app"
```
