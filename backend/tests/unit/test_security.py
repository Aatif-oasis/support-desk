from jose import JWTError

from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_api_key,
    generate_refresh_token,
    hash_api_key,
    hash_password,
    hash_token,
    verify_password,
)


def test_password_hash_and_verify_roundtrip():
    plain = "SuperSecret123"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed) is True


def test_password_verify_rejects_wrong_password():
    hashed = hash_password("SuperSecret123")
    assert verify_password("WrongPassword", hashed) is False


def test_access_token_roundtrip_with_claims():
    token = create_access_token(subject="user-123", extra_claims={"roles": ["org_admin"]})
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"
    assert payload["roles"] == ["org_admin"]
    assert payload["type"] == "access"


def test_decode_access_token_rejects_tampered_token():
    token = create_access_token(subject="user-123")
    tampered = token[:-2] + "xx"
    try:
        decode_access_token(tampered)
        assert False, "expected JWTError for tampered token"
    except JWTError:
        pass


def test_refresh_token_hash_is_deterministic_and_not_reversible():
    token = generate_refresh_token()
    assert hash_token(token) == hash_token(token)
    assert hash_token(token) != token


def test_api_key_format_and_hash():
    key = generate_api_key()
    assert key.startswith("oc_live_")
    assert hash_api_key(key) == hash_api_key(key)
    assert hash_api_key(key) != key
