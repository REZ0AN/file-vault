
from pwdlib import PasswordHash


# Password hashing configuration
password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """
    Convert a plaintext password into a secure Argon2id hash.

    Used during user registration.
    """
    return password_hasher.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """
    Verify a plaintext password against a stored hash.

    Used during user login.
    """
    return password_hasher.verify(
        plain_password,
        hashed_password,
    )
