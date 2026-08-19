# Teste de carga — resultados medidos

Script: `tests/load/locustfile.py` (Locust). Números abaixo foram **medidos
de verdade**, não estimados.

## Ambiente da medição

Importante para calibrar as expectativas: os números abaixo vêm de um
ambiente de teste modesto e **compartilhado** — app, Postgres e Redis
rodando na mesma máquina, com **1 worker** do uvicorn. Um servidor de
produção dedicado, com múltiplos workers e banco em instância separada,
deve entregar bem mais. Trate estes valores como piso, não como teto.

- 1 worker uvicorn (`--workers 1`)
- Postgres 16 e Redis 7 locais, mesma máquina do app
- `OTP_PROVIDER=mock` (sem latência de rede de provedor real de SMS)
- Rate limits desativados para medir a aplicação, não o rate limiter

## Resultados

### 50 usuários simultâneos, 30s

| Endpoint | Reqs | Falhas | Mediana | p95 | Máx |
|---|---|---|---|---|---|
| `POST /register` | 526 | **0%** | 18ms | 140ms | 440ms |
| `POST /validate-cpf` | 526 | **0%** | 11ms | 140ms | 470ms |
| `GET /candidatos` | 223 | **0%** | 14ms | 420ms | 630ms |
| `GET /health` | 173 | **0%** | 4ms | 44ms | 120ms |
| **Agregado** | **1448** | **0%** | **13ms** | **240ms** | **630ms** |

Throughput: ~48 req/s. **Confortável** — latência bem dentro do aceitável.

### 200 usuários simultâneos, 45s

| Endpoint | Reqs | Falhas | Mediana | p95 | Máx |
|---|---|---|---|---|---|
| `POST /register` | 1860 | **0%** | 610ms | 1800ms | 6052ms |
| `POST /validate-cpf` | 1896 | **0%** | 450ms | 1800ms | 6272ms |
| `GET /candidatos` | 851 | **0%** | 520ms | 1700ms | 3765ms |
| `GET /health` | 648 | **0%** | 120ms | 240ms | 466ms |
| **Agregado** | **5255** | **0%** | **500ms** | **1700ms** | **6272ms** |

Throughput: ~116 req/s. **Sem erros, mas latência degradada** — mediana de
meio segundo e cauda de até 6s. Funcional, porém desconfortável para o
usuário final.

## Limites recomendados

- **Até ~50 usuários simultâneos**: opera com folga nesta configuração
  mínima.
- **~200 usuários simultâneos**: é o ponto onde a latência começa a
  incomodar (mediana 500ms, p95 1.7s) apesar de não haver erro. Antes de
  operar aqui, aumente o número de workers (`uvicorn --workers N`, regra
  prática: 2×núcleos+1) e/ou coloque o banco em instância separada.
- **Acima disso**: não foi medido. Não opere às cegas — rode o script de
  novo no ambiente real antes.

Para um clube com alguns milhares de associados, o gargalo provável não é
o pico de simultaneidade e sim o **provedor de SMS**: cada `/register`
dispara uma mensagem, e provedores impõem limites de envio por segundo e
por dia. Verifique a cota contratada antes de divulgar a sondagem para
todos de uma vez — divulgar em lotes é mais seguro que descobrir o limite
do provedor em produção.

## Bugs encontrados por este teste

Os dois foram achados rodando a carga, não lendo código:

1. **`SETEX` com TTL 0** — configurar `OTP_RESEND_COOLDOWN_SECONDS=0`
   (forma legítima de desligar o cooldown) fazia 100% das chamadas a
   `/register` retornarem 500: o Redis recusa TTL zero com "invalid expire
   time". Corrigido em `app/services/otp_service.py` — cooldown zero agora
   simplesmente não grava a chave.
2. **Rate limits hardcoded nas rotas** — `app/api/routes/survey.py` tinha
   os limites fixos no código, ignorando as variáveis `RATE_LIMIT_*` do
   `.env`. Impossível afrouxá-los para teste de carga (ou apertá-los em
   produção) sem editar código. Corrigido: agora vêm de `Settings`, com os
   mesmos valores como default.

## Como rodar

```bash
# Use um banco DEDICADO para carga — o teste grava milhares de associados
# e "queima" CPFs (ficam marcados como já votaram).
createdb sondagem_load

export DATABASE_URL='postgresql+asyncpg://user:pass@localhost:5432/sondagem_load'
export OTP_PROVIDER=mock DEBUG=true
export RATE_LIMIT_REGISTER=1000000/minute RATE_LIMIT_VALIDATE_CPF=1000000/minute
export OTP_RESEND_COOLDOWN_SECONDS=0

alembic upgrade head
python -m scripts.seed_candidatos
uvicorn app.main:app --port 8100 &

locust -f tests/load/locustfile.py --host http://127.0.0.1:8100 \
  --headless -u 50 -r 10 -t 30s
```

**Nunca rode contra produção.**
