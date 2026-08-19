# Ambiente de demonstração

Sobe a aplicação inteira com uma sondagem fictícia já respondida, sem
precisar de conta em provedor de SMS, chave de reCAPTCHA ou qualquer
credencial externa.

> **Todos os dados são inventados.** Os candidatos, associados, CPFs,
> telefones e votos criados por `scripts/seed_demo.py` não correspondem a
> nenhuma pessoa real.
>
> Uma ressalva: os CPFs têm dígito verificador válido, porque senão não
> passariam na validação da própria aplicação. Um CPF com dígito válido é
> indistinguível de um que existe de verdade — então o correto é dizer que
> os dados são fictícios, não que os CPFs não existem.

Este ambiente **não é para produção**. Ele roda com `DEBUG=true`, o que faz
o código do OTP ser escrito em texto puro no log e o reCAPTCHA passar sem
validar. Para subir de verdade, ver [PRODUCAO.md](PRODUCAO.md).

## Subir

```bash
docker compose -f docker-compose.demo.yml up -d --build
docker compose -f docker-compose.demo.yml exec app alembic upgrade head
docker compose -f docker-compose.demo.yml exec app python -m scripts.seed_demo
```

- **Sondagem:** http://localhost:8080
- **Painel:** http://localhost:8080/admin — usuário `admin`, senha `demo1234`
- **API:** http://localhost:8080/api/docs

Portas 8080, 5433 e 6380, num projeto Compose próprio (`sondagem-demo`),
para não conflitar com nada que já esteja rodando na máquina. O arquivo
lido é `.env.demo` — versionado de propósito, porque não há segredo nenhum
nele.

## Passar pelo fluxo

O provider de OTP é o `mock`: nenhum SMS sai, e o código de 6 dígitos vai
para o log do container.

```bash
docker compose -f docker-compose.demo.yml logs -f app | grep "OTP mock"
```

Cadastre-se com um CPF válido **que não esteja no seed** — os 13 do seed já
votaram, e a aplicação recusa CPF repetido, que é justamente uma das regras
que vale a pena ver funcionando. O número de sócio também é único: use
qualquer um fora da faixa `0104`–`1315`.

Para ver a recusa de voto duplicado, use um CPF que está no seed.

## O que o seed cria

- **6 candidatos** fictícios, sem foto (caem no `placeholder.svg`; dá para
  subir imagens pelo painel)
- **13 respostas**, com 32 votos distribuídos de forma desigual — de 10
  votos no mais votado a 2 no último, para o resultado consolidado não sair
  com todas as barras do mesmo tamanho
- **modalidades** variadas por pessoa, incluindo um "Outros" com texto
  livre preenchido, que é o caminho que exige campo complementar

A resposta mais recente é a de `Rafael dos Santos`. Como as consultas
ordenam por data decrescente, ela aparece no topo da busca do painel e na
primeira linha da planilha exportada.

## Rodar de novo do zero

O seed é destrutivo e idempotente: apaga associados, candidatos e votos
antes de recriar. Pode rodar quantas vezes quiser.

```bash
docker compose -f docker-compose.demo.yml exec app python -m scripts.seed_demo
```

Ele se recusa a rodar com `DEBUG=false`, para não haver como apontá-lo para
um banco de produção e apagar dados reais.

Se editar `scripts/seed_demo.py`, rebuilde antes — o código vai embutido na
imagem, não montado do disco:

```bash
docker compose -f docker-compose.demo.yml up -d --build app
```

## Derrubar

```bash
docker compose -f docker-compose.demo.yml down          # mantém o banco
docker compose -f docker-compose.demo.yml down -v       # apaga o banco também
```
