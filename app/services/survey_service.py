import csv
import io
import logging

from openpyxl import Workbook
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Associado,
    AssociadoDepartamento,
    Preferencia,
    Resposta,
)
from app.repositories import (
    AssociadoRepository,
    AuditLogRepository,
    CandidatoRepository,
    DepartamentoRepository,
    PreferenciaRepository,
    RespostaRepository,
)
from app.services.otp_service import OTPService
from app.utils.cpf import format_cpf
from app.utils.datetime_br import format_datetime_br

logger = logging.getLogger(__name__)


def _mensagem_para_erro_de_unicidade(detalhe_erro: str) -> str:
    """
    Escolhe a mensagem certa a partir do texto de uma violação de UNIQUE
    constraint em `associados` (ou seja, `str(exc.orig)` de um
    IntegrityError capturado em `submit_vote`).

    Casa o nome da COLUNA, não o da constraint: o texto do driver traz os
    dois (nome da constraint + "DETAIL: Key (coluna)=..."), e casar pela
    coluna sobrevive a uma renomeação de constraint. É também o único jeito
    que funciona nos dois ambientes ao mesmo tempo — Alembic (produção) nomeia
    a constraint de cpf como "associados_cpf_key", enquanto create_all (usado
    pelos testes) não cria constraint nenhuma para cpf, só o índice único
    "ix_associados_cpf" (efeito colateral de `unique=True` + `index=True`
    juntos no mapeamento); só "numero_socio" tem o mesmo nome de constraint
    nos dois, por ser nomeada explicitamente em `__table_args__`.

    ATENÇÃO: quem chama esta função nunca deve logar `detalhe_erro` — ele
    contém o valor que violou a constraint, ou seja, o CPF completo em
    texto puro.
    """
    if "numero_socio" in detalhe_erro:
        return "Este número de sócio já participou da sondagem"
    return "Este CPF já participou da sondagem"


class SurveyService:
    def __init__(self, db: AsyncSession, otp_service: OTPService) -> None:
        self.db = db
        self.otp_service = otp_service
        self.associado_repo = AssociadoRepository(db)
        self.candidato_repo = CandidatoRepository(db)
        self.resposta_repo = RespostaRepository(db)
        self.preferencia_repo = PreferenciaRepository(db)
        self.departamento_repo = DepartamentoRepository(db)
        self.audit_repo = AuditLogRepository(db)

    async def check_cpf_available(self, cpf: str) -> tuple[bool, str | None]:
        existing = await self.associado_repo.get_by_cpf(cpf)
        if existing:
            return False, "Este CPF já participou da sondagem"
        return True, None

    async def check_numero_socio_available(self, numero_socio: str) -> tuple[bool, str | None]:
        existing = await self.associado_repo.get_by_numero_socio(numero_socio)
        if existing:
            return False, "Este número de sócio já participou da sondagem"
        return True, None

    async def check_telefone_available(self, telefone: str) -> tuple[bool, str | None]:
        existing = await self.associado_repo.get_by_telefone(telefone)
        if existing:
            return False, "Este telefone já participou da sondagem"
        return True, None

    async def register_and_send_otp(
        self,
        nome: str,
        cpf: str,
        telefone: str,
        numero_socio: str,
        titular: bool,
        ip: str | None,
        user_agent: str | None,
    ) -> tuple[str | None, str | None]:
        available, msg = await self.check_cpf_available(cpf)
        if not available:
            return None, msg

        # Checado aqui, e não só no submit, para não gastar um SMS num
        # cadastro que seria rejeitado no fim do fluxo.
        available, msg = await self.check_numero_socio_available(numero_socio)
        if not available:
            return None, msg

        available, msg = await self.check_telefone_available(telefone)
        if not available:
            return None, msg

        session_token = await self.otp_service.create_session(
            {
                "nome": nome,
                "cpf": cpf,
                "telefone": telefone,
                "numero_socio": numero_socio,
                "titular": titular,
                "verified": False,
                "ip": ip,
                "user_agent": user_agent,
            }
        )

        success, error = await self.otp_service.send_otp(telefone)
        if not success:
            await self.otp_service.delete_session(session_token)
            return None, error

        await self.audit_repo.create(
            "otp_sent",
            f"OTP enviado para telefone {telefone[-4:]}",
            ip,
            user_agent,
        )
        return session_token, None

    async def verify_otp(
        self,
        telefone: str,
        codigo: str,
        session_token: str,
        ip: str | None,
        user_agent: str | None,
    ) -> tuple[bool, str | None]:
        session = await self.otp_service.get_session(session_token)
        if not session:
            return False, "Sessão expirada. Reinicie o cadastro."

        if session.get("telefone") != telefone:
            return False, "Telefone não corresponde à sessão"

        valid, error = await self.otp_service.verify_otp(telefone, codigo)
        if not valid:
            await self.audit_repo.create("otp_failed", error, ip, user_agent)
            return False, error

        session["verified"] = True
        await self.otp_service.update_session(session_token, session, ttl=3600)

        await self.audit_repo.create("otp_verified", f"Telefone {telefone[-4:]}", ip, user_agent)
        return True, None

    async def resend_otp(
        self,
        telefone: str,
        session_token: str,
    ) -> tuple[bool, str | None]:
        session = await self.otp_service.get_session(session_token)
        if not session:
            return False, "Sessão expirada. Reinicie o cadastro."

        if session.get("telefone") != telefone:
            return False, "Telefone não corresponde à sessão"

        return await self.otp_service.send_otp(telefone)

    async def submit_vote(
        self,
        session_token: str,
        candidatos_ids: list[int],
        candidato_preferido_id: int,
        departamentos_ids: list[int],
        departamento_outros: str,
        aceite_lgpd: bool,
        ip: str | None,
        user_agent: str | None,
    ) -> tuple[bool, str | None]:
        session = await self.otp_service.get_session(session_token)
        if not session or not session.get("verified"):
            return False, "Sessão inválida ou não autenticada"

        cpf = session["cpf"]
        numero_socio = session["numero_socio"]
        # .get, e não session["titular"]: sessões abertas antes do deploy
        # desta feature não têm a chave, e um KeyError aqui derrubaria o
        # submit de quem estava no meio do fluxo. None é a resposta honesta
        # nesse caso — a pessoa não chegou a ver o checkbox.
        titular = session.get("titular")

        available, msg = await self.check_cpf_available(cpf)
        if not available:
            return False, msg

        available, msg = await self.check_numero_socio_available(numero_socio)
        if not available:
            return False, msg

        available, msg = await self.check_telefone_available(session["telefone"])
        if not available:
            return False, msg

        candidatos = await self.candidato_repo.list_active()
        # Só o conjunto de ids: o mapa id->objeto existia para montar os
        # nomes do payload do webhook, que saiu na migration 008. A validação
        # abaixo precisa apenas saber quais ids estão ativos.
        active_ids = {c.id for c in candidatos}

        if not all(cid in active_ids for cid in candidatos_ids):
            return False, "Um ou mais candidatos selecionados são inválidos"

        if candidato_preferido_id not in active_ids:
            return False, "Candidato preferencial inválido"

        if candidato_preferido_id not in candidatos_ids:
            return False, "O candidato preferencial deve estar entre os selecionados"

        departamentos = await self.departamento_repo.list_active()
        departamento_map = {d.id: d for d in departamentos}

        if not all(did in departamento_map for did in departamentos_ids):
            return False, "Modalidade inválida"

        # Qual opção exige texto é dado do banco (coluna exige_texto), não o
        # nome "Outros" nem um id cravado no código.
        exige_texto = any(
            departamento_map[did].exige_texto for did in departamentos_ids
        )
        texto_outros = departamento_outros.strip()

        if exige_texto and not texto_outros:
            return False, "Descreva qual modalidade em Outros"

        # Sem a opção que exige texto, o campo é descartado: não se guarda
        # texto órfão de quem preencheu e depois desmarcou.
        if not exige_texto:
            texto_outros = ""

        associado = Associado(
            nome=session["nome"],
            cpf=cpf,
            numero_socio=numero_socio,
            telefone=session["telefone"],
            titular=titular,
            departamento_outros=texto_outros or None,
            ip=ip or session.get("ip"),
            user_agent=user_agent or session.get("user_agent"),
            aceite_lgpd=aceite_lgpd,
        )
        try:
            associado = await self.associado_repo.create(associado)
        except IntegrityError as exc:
            # As checagens acima são otimistas — não há lock entre o SELECT e
            # este INSERT, e entre os dois ainda passa todo o fluxo de OTP.
            # As constraints UNIQUE do banco são quem realmente garante um
            # voto por CPF e um por número de sócio; aqui só traduzimos a
            # violação numa mensagem que diz qual dos dois repetiu (ver
            # _mensagem_para_erro_de_unicidade acima para a lógica e o
            # motivo de nunca logar esse texto).
            await self.db.rollback()
            return False, _mensagem_para_erro_de_unicidade(str(exc.orig))

        respostas = [
            Resposta(associado_id=associado.id, candidato_id=cid) for cid in candidatos_ids
        ]
        await self.resposta_repo.create_bulk(respostas)

        await self.preferencia_repo.create(
            Preferencia(
                associado_id=associado.id,
                candidato_preferido_id=candidato_preferido_id,
            )
        )

        self.db.add_all(
            [
                AssociadoDepartamento(
                    associado_id=associado.id, departamento_id=did
                )
                for did in departamentos_ids
            ]
        )
        await self.db.flush()

        await self.otp_service.delete_session(session_token)

        await self.audit_repo.create(
            "vote_submitted",
            f"CPF {cpf[-4:]} votou",
            ip,
            user_agent,
        )
        return True, None


def _rotulo_titular(valor: bool | None) -> str:
    """
    "Sim"/"Não" para quem respondeu; vazio para quem votou antes da pergunta
    existir (titular IS NULL — ver migration 007).

    Três estados e não dois: quem for contar titulares na planilha precisa
    conseguir separar "declarou que não é" de "nunca foi perguntado". Um
    "Não" nas duas situações inflaria a contagem de dependentes com todo o
    histórico anterior à feature.
    """
    if valor is None:
        return ""
    return "Sim" if valor else "Não"


_CABECALHO_RESULTADOS = [
    "Candidato",
    "Apelido",
    "Votos",
    "% dos Respondentes",
    "Ponto Focal",
]


class ExportService:
    def __init__(self, db: AsyncSession) -> None:
        self.associado_repo = AssociadoRepository(db)
        self.candidato_repo = CandidatoRepository(db)

    async def _linhas_resultados(self) -> list[list]:
        """
        Resultado agregado, sem nenhum identificador pessoal: uma linha por
        candidato, com votos, percentual e quantas vezes foi escolhido como
        ponto focal.

        Existe para o caso de quem só precisa do RESULTADO da sondagem —
        quem lidera, quantos votos cada um teve. Nesse caso não há motivo
        para entregar CPF, telefone ou nome de associado, e o aviso de
        privacidade do formulário fala em uso restrito a validação de
        segurança e prevenção de duplicidade. Quem precisar do dado nominal
        continua tendo export_csv/export_excel.
        """
        agregado = await self.candidato_repo.resultado_agregado()
        total_respondentes = await self.associado_repo.count()

        linhas = []
        for candidato, votos, focal in agregado:
            # Guarda de divisão por zero: antes do primeiro voto a sondagem
            # existe e o relatório pode ser baixado.
            percentual = (votos / total_respondentes * 100) if total_respondentes else 0.0
            linhas.append(
                [
                    candidato.nome,
                    candidato.apelido,
                    votos,
                    round(percentual, 1),
                    focal,
                ]
            )
        return linhas

    async def export_csv(self) -> str:
        associados = await self.associado_repo.list_all_with_details()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "ID",
                "Nº Sócio",
                "Nome",
                "CPF",
                "Telefone",
                "Titular",
                "Candidatos",
                "Preferido",
                "Modalidades",
                "Outros (descrição)",
                "Data",
                "LGPD",
            ]
        )

        for a in associados:
            candidatos = ", ".join(r.candidato.nome for r in a.respostas)
            preferido = a.preferencia.candidato_preferido.nome if a.preferencia else ""
            modalidades = ", ".join(
                ad.departamento.nome
                for ad in sorted(a.departamentos, key=lambda x: x.departamento.ordem)
            )
            writer.writerow(
                [
                    a.id,
                    a.numero_socio,
                    a.nome,
                    format_cpf(a.cpf),
                    a.telefone,
                    _rotulo_titular(a.titular),
                    candidatos,
                    preferido,
                    modalidades,
                    a.departamento_outros or "",
                    format_datetime_br(a.data_resposta),
                    "Sim" if a.aceite_lgpd else "Não",
                ]
            )

        return output.getvalue()

    async def export_excel(self) -> bytes:
        associados = await self.associado_repo.list_all_with_details()
        wb = Workbook()
        ws = wb.active
        ws.title = "Respostas"
        ws.append(
            [
                "ID",
                "Nº Sócio",
                "Nome",
                "CPF",
                "Telefone",
                "Titular",
                "Candidatos",
                "Preferido",
                "Modalidades",
                "Outros (descrição)",
                "Data",
                "LGPD",
            ]
        )

        for a in associados:
            candidatos = ", ".join(r.candidato.nome for r in a.respostas)
            preferido = a.preferencia.candidato_preferido.nome if a.preferencia else ""
            modalidades = ", ".join(
                ad.departamento.nome
                for ad in sorted(a.departamentos, key=lambda x: x.departamento.ordem)
            )
            ws.append(
                [
                    a.id,
                    a.numero_socio,
                    a.nome,
                    format_cpf(a.cpf),
                    a.telefone,
                    _rotulo_titular(a.titular),
                    candidatos,
                    preferido,
                    modalidades,
                    a.departamento_outros or "",
                    format_datetime_br(a.data_resposta),
                    "Sim" if a.aceite_lgpd else "Não",
                ]
            )

        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    async def export_resultados_csv(self) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(_CABECALHO_RESULTADOS)
        writer.writerows(await self._linhas_resultados())
        return output.getvalue()

    async def export_resultados_excel(self) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "Resultados"
        ws.append(_CABECALHO_RESULTADOS)
        for linha in await self._linhas_resultados():
            ws.append(linha)

        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()
