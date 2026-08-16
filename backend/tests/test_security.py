from uuid import uuid4

import pytest

from app.core.security import decrypt_token, encrypt_token, issue_session, read_session


def test_token_survives_a_round_trip_but_is_not_stored_in_the_clear():
    ciphertext = encrypt_token("gho_secret")

    assert ciphertext != "gho_secret"
    assert decrypt_token(ciphertext) == "gho_secret"


def test_decrypting_a_corrupted_token_raises():
    with pytest.raises(ValueError):
        decrypt_token("not-a-fernet-token")


def test_session_round_trips_the_user_id():
    user_id = uuid4()

    assert read_session(issue_session(user_id)) == user_id


def test_tampered_session_is_rejected():
    token = issue_session(uuid4())

    assert read_session(token[:-4] + "aaaa") is None
    assert read_session("garbage") is None
