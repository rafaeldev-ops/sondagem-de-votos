from app.utils.sanitize import sanitize_text


class TestSanitizeText:
    def test_strips_script_tags(self):
        result = sanitize_text("<script>alert(1)</script>Fulano")
        assert "<script>" not in result
        assert "Fulano" in result

    def test_strips_event_handler_payload(self):
        # Regressão direta do achado C1 da auditoria: nome de candidato com
        # payload de XSS armazenado precisa sair limpo daqui.
        result = sanitize_text('<img src=x onerror=alert(1)>Fulano')
        assert "onerror" not in result
        assert "<img" not in result

    def test_plain_text_unchanged(self):
        assert sanitize_text("Maria da Silva") == "Maria da Silva"

    def test_respects_max_length(self):
        result = sanitize_text("a" * 300, max_length=50)
        assert len(result) == 50

    def test_strips_leading_trailing_whitespace(self):
        assert sanitize_text("  Maria  ") == "Maria"
