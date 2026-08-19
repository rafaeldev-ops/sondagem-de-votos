"""
Regressão: as fotos dos candidatos eram gravadas num diretório que não
sobrevive ao container.

`_save_photo` escrevia num caminho fixo no código, `static/uploads/candidatos`,
ignorando o `UPLOAD_DIR` do .env. Só que `static/` vem da imagem — o único
diretório persistido é o do `UPLOAD_DIR`, montado pelo docker-compose em
`./uploads:/app/uploads`. Resultado: a foto ia para a camada de escrita do
container e era descartada no `docker compose up --build` / `--force-recreate`
seguinte.

As linhas do banco sobreviviam (o Postgres tem volume nomeado) apontando para
arquivos que não existiam mais, então todo `<img>` do site virava ícone de
imagem quebrada — 29 candidatos, todos com HTTP 404 na foto. E era silencioso:
nada falhava no upload, o defeito só aparecia depois do rebuild seguinte.

O que estes testes travam é que o destino da gravação e a URL devolvida saem
ambos do `UPLOAD_DIR` — que é o caminho persistido e o mesmo que
`app/main.py` monta em `/uploads`.
"""

import io

import pytest
from fastapi import UploadFile

from app.services.admin_service import AdminService

# Assinatura real de JPEG: `_save_photo` valida os magic bytes, então um
# conteúdo qualquer seria recusado antes de chegar na gravação.
JPEG = b"\xff\xd8\xff\xe0" + b"conteudo irrelevante para o teste"


def _upload(filename: str = "retrato.jpg", conteudo: bytes = JPEG) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(conteudo))


@pytest.fixture
def service(tmp_path):
    """
    AdminService com UPLOAD_DIR apontando para um diretório descartável.

    `db=None` basta: `_save_photo` não toca no banco. E o tmp_path é o que
    dá sentido ao teste — com o caminho fixo antigo, a gravação acontecia
    em `static/uploads/candidatos` relativo ao cwd e nada aparecia aqui.
    """
    svc = AdminService(db=None)
    svc.settings = svc.settings.model_copy(
        update={"upload_dir": str(tmp_path / "uploads" / "candidatos")}
    )
    return svc


class TestSavePhoto:
    @pytest.mark.asyncio
    async def test_grava_no_diretorio_do_upload_dir(self, service, tmp_path):
        """O arquivo tem que existir no caminho persistido, não em static/."""
        await service._save_photo(_upload())

        destino = tmp_path / "uploads" / "candidatos"
        gravados = list(destino.glob("*.jpg"))
        assert len(gravados) == 1, f"esperava 1 arquivo em {destino}, achei {gravados}"
        assert gravados[0].read_bytes() == JPEG

    @pytest.mark.asyncio
    async def test_url_devolvida_aponta_para_o_arquivo_gravado(self, service, tmp_path):
        """
        A URL é o que vai no <img src> do site. Ela precisa resolver para o
        arquivo que acabou de ser escrito, através do mount `/uploads` que
        `app/main.py` publica em cima do UPLOAD_DIR.
        """
        url = await service._save_photo(_upload())

        assert url.startswith("/uploads/"), f"URL fora do mount persistido: {url}"
        arquivo = tmp_path / "uploads" / "candidatos" / url.removeprefix("/uploads/")
        assert arquivo.is_file(), f"{url} não corresponde a nenhum arquivo gravado"

    @pytest.mark.asyncio
    async def test_cria_o_diretorio_quando_ainda_nao_existe(self, service, tmp_path):
        """
        Num ambiente novo o subdiretório do UPLOAD_DIR pode não existir (o git
        versiona só `uploads/.gitkeep`). O upload não pode falhar por isso.
        """
        assert not (tmp_path / "uploads" / "candidatos").exists()

        url = await service._save_photo(_upload())

        assert (tmp_path / "uploads" / "candidatos" / url.rsplit("/", 1)[-1]).is_file()

    @pytest.mark.asyncio
    async def test_preserva_a_extensao_do_arquivo_enviado(self, service, tmp_path):
        """PNG precisa continuar .png: o navegador serve pelo nome do arquivo."""
        png = b"\x89PNG\r\n\x1a\n" + b"conteudo"

        url = await service._save_photo(_upload("foto.png", png))

        assert url.endswith(".png")
        assert (tmp_path / "uploads" / "candidatos" / url.rsplit("/", 1)[-1]).is_file()

    @pytest.mark.asyncio
    async def test_recusa_formato_nao_permitido_sem_gravar_nada(self, service, tmp_path):
        """A validação de extensão continua valendo depois da mudança."""
        with pytest.raises(ValueError, match="Formato de imagem não permitido"):
            await service._save_photo(_upload("script.svg", JPEG))

        destino = tmp_path / "uploads" / "candidatos"
        assert not destino.exists() or not list(destino.iterdir())
