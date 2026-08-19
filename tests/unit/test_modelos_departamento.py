"""
O schema dos departamentos é criado por Alembic em produção e por
create_all nos testes. Estes testes travam os nomes de constraint e a
presença dos índices, que são exatamente o que diverge entre os dois
ambientes quando alguém esquece de declarar no modelo.
"""

from app.models import Associado, AssociadoDepartamento, Departamento


class TestTabelaDepartamentos:
    def test_nome_da_tabela(self):
        assert Departamento.__tablename__ == "departamentos"

    def test_constraint_unica_tem_nome_explicito(self):
        nomes = {c.name for c in Departamento.__table__.constraints if c.name}
        assert "uq_departamentos_nome" in nomes

    def test_colunas_esperadas(self):
        colunas = set(Departamento.__table__.columns.keys())
        assert colunas == {"id", "nome", "ordem", "exige_texto", "ativo", "created_at"}


class TestTabelaAssociativa:
    def test_nome_da_tabela(self):
        assert AssociadoDepartamento.__tablename__ == "associado_departamentos"

    def test_constraint_unica_tem_nome_explicito(self):
        nomes = {c.name for c in AssociadoDepartamento.__table__.constraints if c.name}
        assert "uq_associado_departamento" in nomes

    def test_as_duas_fks_sao_indexadas(self):
        """Postgres não indexa coluna de FK sozinho, e a exportação faz join
        pelas duas. Declarado no modelo para que create_all e Alembic gerem
        o mesmo schema."""
        indexadas = {
            col.name
            for idx in AssociadoDepartamento.__table__.indexes
            for col in idx.columns
        }
        assert indexadas == {"associado_id", "departamento_id"}


class TestColunaEmAssociado:
    def test_departamento_outros_e_nullable(self):
        coluna = Associado.__table__.columns["departamento_outros"]
        assert coluna.nullable is True
        assert coluna.type.length == 100
