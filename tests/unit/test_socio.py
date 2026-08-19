import pytest

from app.utils.socio import normalize_numero_socio, validate_numero_socio


class TestNormalizeNumeroSocio:
    def test_remove_mascara_e_espacos(self):
        assert normalize_numero_socio(" 00-42 ") == "0042"

    def test_mantem_digitos_puros_inalterados(self):
        assert normalize_numero_socio("1234") == "1234"

    def test_string_sem_digitos_vira_vazia(self):
        assert normalize_numero_socio("abcd") == ""


class TestValidateNumeroSocio:
    @pytest.mark.parametrize("valor", ["0001", "9999", "0042", "1234"])
    def test_aceita_quatro_digitos(self, valor):
        assert validate_numero_socio(valor) is True

    def test_preserva_zeros_a_esquerda(self):
        """0042 e 42 sao socios diferentes — por isso o campo e texto, nao int."""
        assert validate_numero_socio("0042") is True
        assert validate_numero_socio("42") is False

    @pytest.mark.parametrize("valor", ["123", "12345", "", "abcd", "12a4", "12 4"])
    def test_rejeita_formato_invalido(self, valor):
        assert validate_numero_socio(valor) is False

    @pytest.mark.parametrize("valor", ["٤٢٣١", "²²²²", "١٢٣٤"])
    def test_rejeita_digitos_unicode(self, valor):
        """
        A premissa deste teste e que str.isdigit() aceita esses caracteres —
        e por isso que a validacao usa re.fullmatch(r"[0-9]{4}"). A primeira
        asserta a armadilha (se um dia deixar de valer, o teste avisa em vez
        de virar tautologia); a segunda asserta o comportamento.
        """
        assert valor.isdigit() is True
        assert validate_numero_socio(valor) is False
