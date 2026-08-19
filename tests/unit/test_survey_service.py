"""
Cobre duas coisas que tests/integration/test_numero_socio.py não alcança:

1. A lógica de app.services.survey_service._mensagem_para_erro_de_unicidade,
   que só roda dentro do `except IntegrityError` de `submit_vote` — ou seja,
   só numa corrida de verdade entre duas requisições concorrentes com o
   mesmo CPF ou número de sócio. Isso não é reproduzível de forma
   determinística num teste de integração (a checagem otimista antes do
   INSERT já barra os casos de uso normal do fluxo), então a função foi
   extraída para poder ser chamada direto, com strings de erro reais do
   asyncpg em vez de depender da corrida acontecer.

2. Que a constraint UNIQUE de numero_socio continua nomeada
   "uq_associados_numero_socio" no modelo — é esse nome que
   _mensagem_para_erro_de_unicidade e a migration 004 precisam bater. Sem
   isso, remover __table_args__ (ou renomear a constraint) não quebra
   nenhum teste, e silenciosamente muda o comportamento em produção: um
   numero_socio repetido passaria a cair no "Este CPF já participou da
   sondagem" (ver comentário da função).
"""

from app.models import Associado
from app.services.survey_service import _mensagem_para_erro_de_unicidade


class TestMensagemParaErroDeUnicidade:
    # Formato real do asyncpg 0.30 / SQLAlchemy 2.0.36, como aparece em
    # str(exc.orig): "duplicate key value violates unique constraint
    # \"<nome>\"\nDETAIL:  Key (<coluna>)=(<valor>) already exists."
    NUMERO_SOCIO = (
        'duplicate key value violates unique constraint "uq_associados_numero_socio"\n'
        "DETAIL:  Key (numero_socio)=(0042) already exists."
    )
    # Alembic (produção) nomeia a constraint de cpf como "associados_cpf_key".
    CPF_PRODUCAO = (
        'duplicate key value violates unique constraint "associados_cpf_key"\n'
        "DETAIL:  Key (cpf)=(12345678901) already exists."
    )
    # create_all (usado pelos testes) não cria constraint nenhuma para cpf —
    # unique=True + index=True gera só um índice único, "ix_associados_cpf".
    CPF_TESTES = (
        'duplicate key value violates unique constraint "ix_associados_cpf"\n'
        "DETAIL:  Key (cpf)=(12345678901) already exists."
    )

    def test_numero_socio_repetido(self):
        assert (
            _mensagem_para_erro_de_unicidade(self.NUMERO_SOCIO)
            == "Este número de sócio já participou da sondagem"
        )

    def test_cpf_repetido_com_o_nome_de_constraint_de_producao(self):
        assert (
            _mensagem_para_erro_de_unicidade(self.CPF_PRODUCAO)
            == "Este CPF já participou da sondagem"
        )

    def test_cpf_repetido_com_o_nome_de_indice_de_testes(self):
        """
        As duas spellings de cpf (constraint em produção, índice nos testes)
        precisam cair na mesma mensagem — é por isso que a função casa pelo
        nome da COLUNA, não da constraint/índice.
        """
        assert (
            _mensagem_para_erro_de_unicidade(self.CPF_TESTES)
            == "Este CPF já participou da sondagem"
        )


class TestConstraintUnicaDoNumeroSocio:
    def test_constraint_esta_nomeada_uq_associados_numero_socio(self):
        """
        Fixa o nome usado tanto por _mensagem_para_erro_de_unicidade quanto
        pela migration 004. Se __table_args__ for removido (voltando para
        unique=True inline na coluna) ou a constraint for renomeada, este
        teste falha em vez de deixar a mudança passar batido — o cenário
        real seria numero_socio repetido virando "Este CPF já participou
        da sondagem" em produção.
        """
        nomes_e_colunas = {
            c.name: {col.name for col in c.columns}
            for c in Associado.__table__.constraints
            if type(c).__name__ == "UniqueConstraint"
        }
        assert nomes_e_colunas.get("uq_associados_numero_socio") == {"numero_socio"}
