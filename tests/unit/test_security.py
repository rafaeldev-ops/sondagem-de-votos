from datetime import timedelta

from app.core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        hashed = get_password_hash("minhasenha123")
        assert hashed != "minhasenha123"
        assert hashed.startswith("$2")  # prefixo bcrypt

    def test_verify_correct_password(self):
        hashed = get_password_hash("minhasenha123")
        assert verify_password("minhasenha123", hashed) is True

    def test_verify_wrong_password(self):
        hashed = get_password_hash("minhasenha123")
        assert verify_password("senhaerrada", hashed) is False

    def test_two_hashes_of_same_password_differ(self):
        # bcrypt usa salt aleatório — hashes do mesmo texto nunca são iguais
        h1 = get_password_hash("mesma-senha")
        h2 = get_password_hash("mesma-senha")
        assert h1 != h2


class TestJwt:
    def test_roundtrip(self):
        token = create_access_token({"sub": "admin"})
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "admin"

    def test_invalid_token_returns_none(self):
        assert decode_access_token("token.invalido.aqui") is None

    def test_tampered_token_rejected(self):
        token = create_access_token({"sub": "admin"})
        tampered = token[:-4] + "abcd"
        assert decode_access_token(tampered) is None

    def test_expired_token_rejected(self):
        token = create_access_token({"sub": "admin"}, expires_delta=timedelta(seconds=-1))
        assert decode_access_token(token) is None
