import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Candidato
from app.repositories import AssociadoRepository, CandidatoRepository
from app.utils.sanitize import sanitize_text

# Assinaturas de arquivo (magic bytes) para os formatos permitidos.
# Checar apenas a extensão do nome do arquivo é insuficiente — qualquer
# arquivo pode ser renomeado para .png. Isso valida o conteúdo real.
_MAGIC_BYTES: dict[str, tuple[bytes, ...]] = {
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".webp": (b"RIFF",),  # bytes 8-12 == b"WEBP", checado à parte abaixo
}


class AdminService:
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.candidato_repo = CandidatoRepository(db)
        self.associado_repo = AssociadoRepository(db)
        self.settings = get_settings()

    async def get_stats(self) -> dict:
        return {
            "total_respostas": await self.associado_repo.count(),
            "total_candidatos_ativos": await self.candidato_repo.count_active(),
            "total_candidatos": await self.candidato_repo.count_all(),
        }

    async def list_candidatos(self) -> list[Candidato]:
        return await self.candidato_repo.list_all()

    async def create_candidato(
        self,
        nome: str,
        apelido: str,
        ativo: bool = True,
        foto: UploadFile | None = None,
    ) -> Candidato:
        foto_path = None
        if foto and foto.filename:
            foto_path = await self._save_photo(foto)

        # Sanitização aplicada aqui (não só no schema Pydantic) para que
        # qualquer rota que chame este service — atual ou futura — fique
        # protegida contra XSS armazenado, independentemente de como o
        # parâmetro chegou (Form, JSON, etc).
        candidato = Candidato(
            nome=sanitize_text(nome, max_length=150),
            apelido=sanitize_text(apelido, max_length=80),
            foto=foto_path,
            ativo=ativo,
        )
        return await self.candidato_repo.create(candidato)

    async def update_candidato(
        self,
        candidato_id: int,
        nome: str | None = None,
        apelido: str | None = None,
        ativo: bool | None = None,
        foto: UploadFile | None = None,
    ) -> Candidato | None:
        candidato = await self.candidato_repo.get_by_id(candidato_id)
        if not candidato:
            return None

        if nome is not None:
            candidato.nome = sanitize_text(nome, max_length=150)
        if apelido is not None:
            candidato.apelido = sanitize_text(apelido, max_length=80)
        if ativo is not None:
            candidato.ativo = ativo
        if foto and foto.filename:
            candidato.foto = await self._save_photo(foto)

        return await self.candidato_repo.update(candidato)

    async def _save_photo(self, foto: UploadFile) -> str:
        ext = Path(foto.filename or "").suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValueError("Formato de imagem não permitido")

        # UPLOAD_DIR, e não `static/`: `static/` vem da imagem, então gravar
        # lá deixa a foto na camada de escrita do container e o próximo
        # `--build`/`--force-recreate` a descarta. O UPLOAD_DIR é o caminho
        # que o docker-compose monta em disco (`./uploads:/app/uploads`) e o
        # mesmo que app/main.py publica no mount `/uploads` — por isso a URL
        # devolvida abaixo tem esse prefixo.
        upload_dir = Path(self.settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = upload_dir / filename

        content = await foto.read()
        max_size = self.settings.max_upload_size_mb * 1024 * 1024
        if len(content) > max_size:
            raise ValueError(f"Arquivo excede {self.settings.max_upload_size_mb}MB")

        self._validate_magic_bytes(content, ext)

        with open(filepath, "wb") as f:
            f.write(content)

        return f"/uploads/{filename}"

    @staticmethod
    def _validate_magic_bytes(content: bytes, ext: str) -> None:
        """Confere a assinatura real do arquivo, não só a extensão do nome."""
        signatures = _MAGIC_BYTES.get(ext, ())
        if not any(content.startswith(sig) for sig in signatures):
            raise ValueError("Conteúdo do arquivo não corresponde ao formato declarado")
        if ext == ".webp" and content[8:12] != b"WEBP":
            raise ValueError("Conteúdo do arquivo não corresponde ao formato declarado")

    async def search_cpf(self, cpf: str) -> list:
        return await self.associado_repo.search_by_cpf(cpf)
