from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Associado(Base):
    __tablename__ = "associados"
    # Constraint nomeada explicitamente porque Base.metadata não tem
    # naming_convention: com unique=True inline, create_all (usado pelos
    # testes) geraria "associados_numero_socio_key" e o Alembic
    # "uq_associados_numero_socio". A lógica que distingue qual constraint
    # estourou depende de os dois ambientes concordarem.
    __table_args__ = (
        UniqueConstraint("numero_socio", name="uq_associados_numero_socio"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    cpf: Mapped[str] = mapped_column(String(11), unique=True, nullable=False, index=True)
    # Texto, não inteiro: zeros à esquerda são significativos (0042 != 42).
    numero_socio: Mapped[str] = mapped_column(String(4), nullable=False)
    telefone: Mapped[str] = mapped_column(String(20), nullable=False)
    # Sócio titular do grupo familiar (vs. dependente). Declarado pelo próprio
    # associado na etapa 1 — não é validado contra cadastro do clube.
    #
    # Nullable de propósito: NULL significa "não perguntado", e é o que fica
    # nas respostas coletadas antes desta pergunta existir. Um default False
    # na migration transformaria todo mundo que já votou em "não titular" —
    # uma resposta que ninguém deu. A partir daqui toda linha nova grava True
    # ou False de verdade, porque o checkbox é obrigatório no cadastro.
    titular: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    aceite_lgpd: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Preenchido só por quem marcou a modalidade que exige texto ("Outros").
    # Um texto por pessoa, não por modalidade — daí ficar aqui e não em
    # AssociadoDepartamento.
    departamento_outros: Mapped[str | None] = mapped_column(String(100), nullable=True)
    data_resposta: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    respostas: Mapped[list["Resposta"]] = relationship(back_populates="associado")
    preferencia: Mapped["Preferencia | None"] = relationship(back_populates="associado")
    departamentos: Mapped[list["AssociadoDepartamento"]] = relationship(
        back_populates="associado"
    )


class Candidato(Base):
    __tablename__ = "candidatos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    apelido: Mapped[str] = mapped_column(String(100), nullable=False)
    foto: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    respostas: Mapped[list["Resposta"]] = relationship(back_populates="candidato")


class Resposta(Base):
    __tablename__ = "respostas"
    __table_args__ = (UniqueConstraint("associado_id", "candidato_id", name="uq_resposta_associado_candidato"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    associado_id: Mapped[int] = mapped_column(ForeignKey("associados.id"), nullable=False)
    candidato_id: Mapped[int] = mapped_column(ForeignKey("candidatos.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    associado: Mapped["Associado"] = relationship(back_populates="respostas")
    candidato: Mapped["Candidato"] = relationship(back_populates="respostas")


class Preferencia(Base):
    __tablename__ = "preferencias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    associado_id: Mapped[int] = mapped_column(
        ForeignKey("associados.id"),
        unique=True,
        nullable=False,
    )
    candidato_preferido_id: Mapped[int] = mapped_column(ForeignKey("candidatos.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    associado: Mapped["Associado"] = relationship(back_populates="preferencia")
    candidato_preferido: Mapped["Candidato"] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evento: Mapped[str] = mapped_column(String(100), nullable=False)
    detalhes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Departamento(Base):
    __tablename__ = "departamentos"
    __table_args__ = (UniqueConstraint("nome", name="uq_departamentos_nome"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    # Ordem de exibição explícita, e não ORDER BY nome: a collation do banco
    # (en_US.utf8) ordena "Volei Masculino" longe dos outros dois "Vôlei", e o
    # resultado pode variar entre desenvolvimento e produção. A ordem é um
    # dado, não um efeito colateral do ambiente.
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    # True só para "Outros". Marca a opção que exige texto complementar; o
    # serviço consulta esta coluna em vez de comparar nome == "Outros", que
    # quebraria silenciosamente numa renomeação ou correção de acento.
    exige_texto: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    associados: Mapped[list["AssociadoDepartamento"]] = relationship(
        back_populates="departamento"
    )


class AssociadoDepartamento(Base):
    __tablename__ = "associado_departamentos"
    __table_args__ = (
        UniqueConstraint(
            "associado_id", "departamento_id", name="uq_associado_departamento"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # index=True nas duas: Postgres não indexa FK sozinho e a exportação faz
    # join pelas duas. No modelo, não só na migration, para que create_all
    # (testes) e Alembic (produção) concordem.
    associado_id: Mapped[int] = mapped_column(
        ForeignKey("associados.id"), nullable=False, index=True
    )
    departamento_id: Mapped[int] = mapped_column(
        ForeignKey("departamentos.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    associado: Mapped["Associado"] = relationship(back_populates="departamentos")
    departamento: Mapped["Departamento"] = relationship(back_populates="associados")
