from app.utils.cpf import format_cpf, normalize_cpf, validate_cpf


class TestValidateCpf:
    def test_valid_cpf_passes(self, valid_cpf):
        cpf = valid_cpf()
        assert validate_cpf(cpf) is True

    def test_valid_cpf_with_formatting_passes(self, valid_cpf):
        cpf = valid_cpf()
        formatted = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
        assert validate_cpf(normalize_cpf(formatted)) is True

    def test_wrong_check_digits_fails(self, valid_cpf):
        cpf = valid_cpf()
        # Corrompe o último dígito verificador
        broken = cpf[:-1] + str((int(cpf[-1]) + 1) % 10)
        assert validate_cpf(broken) is False

    def test_wrong_length_fails(self):
        assert validate_cpf("123456789") is False
        assert validate_cpf("123456789012") is False

    def test_all_repeated_digits_fails(self):
        # 11111111111 etc passam no cálculo do dígito verificador mas são
        # sempre inválidos na prática (CPFs reais nunca são sequências
        # repetidas) — regra de negócio extra além do cálculo matemático.
        for d in "0123456789":
            assert validate_cpf(d * 11) is False

    def test_empty_string_fails(self):
        assert validate_cpf("") is False


class TestNormalizeCpf:
    def test_strips_non_digits(self):
        assert normalize_cpf("123.456.789-09") == "12345678909"

    def test_already_normalized_unchanged(self):
        assert normalize_cpf("12345678909") == "12345678909"


class TestFormatCpf:
    def test_formats_plain_digits(self):
        assert format_cpf("12345678909") == "123.456.789-09"
