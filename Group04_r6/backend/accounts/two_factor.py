import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    secret_key = settings.SECRET_KEY
    if not secret_key:
        raise RuntimeError("SECRET_KEY must be configured to protect TOTP secrets.")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())
    return Fernet(key)


def encrypt_totp_secret(secret):
    return _fernet().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_totp_secret(encrypted_secret):
    try:
        return _fernet().decrypt(encrypted_secret.encode("ascii")).decode("ascii")
    except InvalidToken as error:
        raise ValueError("The stored TOTP secret cannot be decrypted.") from error


def generate_totp_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def totp_code(secret, timestamp=None):
    counter = int((timestamp if timestamp is not None else time.time()) // 30)
    key = base64.b32decode(secret, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def verify_totp(secret, code, timestamp=None):
    if (
        not isinstance(code, str)
        or len(code) != 6
        or not code.isascii()
        or not code.isdigit()
    ):
        return False
    now = time.time() if timestamp is None else timestamp
    return any(
        hmac.compare_digest(totp_code(secret, now + offset * 30), code)
        for offset in (-1, 0, 1)
    )


def generate_recovery_codes(count=10):
    return [secrets.token_hex(10).upper() for _ in range(count)]


def hash_recovery_code(code):
    key = settings.SECRET_KEY.encode("utf-8")
    normalized_code = "".join(code.split()).upper()
    return hmac.new(key, normalized_code.encode("ascii"), hashlib.sha256).hexdigest()


def provisioning_uri(secret, email):
    issuer = "Group04"
    label = f"{quote(issuer)}:{quote(email, safe='')}"
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
        "&algorithm=SHA1&digits=6&period=30"
    )


def is_administrator(user):
    return (
        user.is_authenticated
        and (
            user.is_staff
            or user.is_superuser
            or user.roles.filter(name="Administrator").exists()
        )
    )
