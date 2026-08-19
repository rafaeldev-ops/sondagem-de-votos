# Documentação da API

Base URL: `/api`

Autenticação admin: `Authorization: Bearer <token>`

## Endpoints Públicos (Sondagem)

### POST `/survey/validate-cpf`

Valida CPF e verifica disponibilidade.

**Body:**
```json
{ "cpf": "12345678909" }
```

**Response 200:**
```json
{
  "valid": true,
  "available": true,
  "message": null
}
```

---

### POST `/survey/register`

Cadastra associado e envia OTP.

**Rate limit:** 10/min

**Body:**
```json
{
  "nome": "João Silva",
  "cpf": "12345678909",
  "numero_socio": "1234",
  "telefone": "11999998888",
  "recaptcha_token": "..."
}
```

**Response 200:**
```json
{
  "session_token": "abc...",
  "message": "Código OTP enviado para seu celular"
}
```

---

### POST `/survey/verify-otp`

Verifica código OTP.

**Body:**
```json
{
  "telefone": "11999998888",
  "codigo": "123456",
  "session_token": "abc..."
}
```

---

### POST `/survey/resend-otp`

Reenvia OTP (cooldown 60s).

**Body:**
```json
{
  "telefone": "11999998888",
  "session_token": "abc..."
}
```

---

### GET `/survey/candidatos`

Lista candidatos ativos.

**Response:**
```json
[
  {
    "id": 1,
    "nome": "Maria Santos",
    "apelido": "Mari",
    "foto": "/uploads/abc.jpg"
  }
]
```

---

### GET `/survey/departamentos`

Lista modalidades/departamentos ativos.

**Response:**
```json
[
  {
    "id": 1,
    "nome": "Natação"
  }
]
```

---

### POST `/survey/submit`

Registra o voto.

**Body:**
```json
{
  "session_token": "abc...",
  "candidatos_ids": [1, 2, 3],
  "candidato_preferido_id": 2,
  "departamentos_ids": [1, 4],
  "departamento_outros": "",
  "aceite_lgpd": true
}
```

| Campo | Obrigatório | Descrição |
|-------|-------------|-----------|
| departamentos_ids | Sim, ao menos 1 | IDs das modalidades frequentadas |
| departamento_outros | Não | Texto livre (máx. 100 caracteres), usado quando a modalidade "Outros" está entre os IDs enviados |

---

## Endpoints Admin

### POST `/admin/login`

**Body:**
```json
{
  "username": "admin",
  "password": "senha"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

---

### GET `/admin/stats`

Retorna estatísticas gerais.

---

### GET `/admin/candidatos`

Lista todos os candidatos.

---

### POST `/admin/candidatos`

Cria candidato (multipart/form-data).

| Campo | Tipo |
|-------|------|
| nome | string |
| apelido | string |
| ativo | boolean |
| foto | file (opcional) |

---

### PUT `/admin/candidatos/{id}`

Atualiza candidato (multipart/form-data).

---

### GET `/admin/search?cpf=123`

Busca associado por CPF parcial.

---

### GET `/admin/export/csv`

Exporta respostas em CSV.

---

### GET `/admin/export/excel`

Exporta respostas em Excel (.xlsx).

---

### GET `/admin/export/resultados/csv`

Exporta o resultado consolidado em CSV: uma linha por pré-candidato, com
votos, percentual sobre os respondentes e quantas vezes foi escolhido como
ponto focal. **Não contém identificador pessoal** — é a exportação indicada
para compartilhar fora do clube.

---

### GET `/admin/export/resultados/excel`

O mesmo conteúdo em Excel (.xlsx).

---

## Health Check

### GET `/health`

```json
{ "status": "ok" }
```

## Códigos de Erro

| Código | Descrição |
|--------|-----------|
| 400 | Validação falhou / CPF já votou / OTP inválido |
| 401 | Token admin inválido |
| 429 | Rate limit excedido |

## Swagger

Disponível em `/api/docs` quando `DEBUG=true`.
