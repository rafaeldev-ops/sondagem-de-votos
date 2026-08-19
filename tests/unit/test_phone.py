from app.utils.phone import format_phone, normalize_phone, validate_phone


class TestNormalizePhone:
    def test_strips_formatting(self):
        assert normalize_phone("(11) 98888-7777") == "11988887777"

    def test_strips_country_code(self):
        assert normalize_phone("+55 11 98888-7777") == "11988887777"


class TestValidatePhone:
    def test_valid_mobile_with_nine(self):
        assert validate_phone("11988887777") is True

    def test_valid_landline(self):
        assert validate_phone("1133334444") is True

    def test_mobile_without_nine_prefix_fails(self):
        # celular de 11 dígitos precisa ter o "9" na 3a posição
        assert validate_phone("11888887777") is False

    def test_wrong_length_fails(self):
        assert validate_phone("119888877") is False
        assert validate_phone("119888877771") is False


class TestFormatPhone:
    def test_formats_mobile(self):
        assert format_phone("11988887777") == "(11) 98888-7777"

    def test_formats_landline(self):
        assert format_phone("1133334444") == "(11) 3333-4444"
