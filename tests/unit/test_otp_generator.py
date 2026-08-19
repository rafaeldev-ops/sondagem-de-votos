from app.utils.otp_generator import generate_otp


class TestGenerateOtp:
    def test_default_length_is_six(self):
        assert len(generate_otp()) == 6

    def test_custom_length(self):
        assert len(generate_otp(length=4)) == 4

    def test_only_digits(self):
        code = generate_otp()
        assert code.isdigit()

    def test_reasonably_random(self):
        # Não é um teste estatístico rigoroso — só garante que não está
        # sempre gerando o mesmo código (ex: seed fixo por engano).
        codes = {generate_otp() for _ in range(50)}
        assert len(codes) > 40
