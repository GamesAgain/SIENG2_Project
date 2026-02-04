from __future__ import annotations

from app.utils.exceptions import StegoEngineError

"""
Asymmetric (RSA) cryptographic utilities for Adaptive Steganography Engine v3.0.0.

Implements:

- RSA key pair generation.
- Saving/loading private & public keys as PEM.
- RSA-OAEP encryption/decryption for a symmetric key K.
- Public key fingerprinting (SHA-256 over DER).

All errors are wrapped as StegoEngineError with descriptive messages.
"""

from pathlib import Path
from typing import Optional, Tuple

import hashlib
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding




RSAPrivateKey = rsa.RSAPrivateKey
RSAPublicKey = rsa.RSAPublicKey


def generate_rsa_keypair(key_size: int = 3072) -> Tuple[RSAPrivateKey, RSAPublicKey]:
    """
    Generate an RSA key pair.

    :param key_size: Key size in bits (e.g., 2048, 3072).
    :return: (private_key, public_key)
    """
    if key_size < 3072:
        raise StegoEngineError("generate_rsa_keypair: key_size must be >= 2048 bits.")
    try:
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
        )
    except ValueError as exc:
        raise StegoEngineError(f"generate_rsa_keypair failed: {exc}") from exc

    public_key = private_key.public_key()
    return private_key, public_key


def save_private_key_pem(
    private_key: RSAPrivateKey,
    path: str,
    password: Optional[str] = None,
) -> None:
    """
    Save a private RSA key in PKCS#8 PEM format.

    :param private_key: RSA private key.
    :param path: Output path for the PEM file.
    :param password: Optional password for encrypting the PEM. If None, no encryption.
    """
    pem_path = Path(path)
    if password is not None and not isinstance(password, str):
        raise StegoEngineError("save_private_key_pem: password must be str or None.")

    if password is None:
        enc_algo = serialization.NoEncryption()
        password_bytes = None
    else:
        password_bytes = password.encode("utf-8")
        enc_algo = serialization.BestAvailableEncryption(password_bytes)

    try:
        pem_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=enc_algo,
        )
        pem_path.write_bytes(pem_bytes)
    except OSError as exc:
        raise StegoEngineError(f"Failed to write private key PEM: {exc}") from exc
    except ValueError as exc:
        raise StegoEngineError(f"Failed to serialize private key: {exc}") from exc


def save_public_key_pem(public_key: RSAPublicKey, path: str) -> None:
    """
    Save a public RSA key in SubjectPublicKeyInfo PEM format.

    :param public_key: RSA public key.
    :param path: Output path for the PEM file.
    """
    pem_path = Path(path)
    try:
        pem_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        pem_path.write_bytes(pem_bytes)
    except OSError as exc:
        raise StegoEngineError(f"Failed to write public key PEM: {exc}") from exc
    except ValueError as exc:
        raise StegoEngineError(f"Failed to serialize public key: {exc}") from exc


def load_private_key_pem(path: str, password: Optional[str] = None) -> RSAPrivateKey:
    """
    Load a private RSA key from a PEM file.

    :param path: PEM file path.
    :param password: Optional password for encrypted PEM (str). None for unencrypted.
    :return: RSAPrivateKey instance.
    """
    pem_path = Path(path)
    if not pem_path.is_file():
        raise StegoEngineError(f"Private key PEM not found: {pem_path}")

    if password is None:
        password_bytes = None
    else:
        if not isinstance(password, str):
            raise StegoEngineError("load_private_key_pem: password must be str or None.")
        password_bytes = password.encode("utf-8")

    try:
        pem_bytes = pem_path.read_bytes()
    except OSError as exc:
        raise StegoEngineError(f"Failed to read private key PEM: {exc}") from exc

    try:
        key = serialization.load_pem_private_key(
            pem_bytes,
            password=password_bytes,
        )
    except (ValueError, TypeError) as exc:
        raise StegoEngineError(
            f"Failed to load private key (wrong password or invalid PEM): {exc}"
        ) from exc

    if not isinstance(key, rsa.RSAPrivateKey):
        raise StegoEngineError("Loaded key is not an RSA private key.")
    return key


def load_public_key_pem(path: str) -> RSAPublicKey:
    """
    Load a public RSA key from a PEM file.

    :param path: PEM file path.
    :return: RSAPublicKey instance.
    """
    pem_path = Path(path)
    if not pem_path.is_file():
        raise StegoEngineError(f"Public key PEM not found: {pem_path}")

    try:
        pem_bytes = pem_path.read_bytes()
    except OSError as exc:
        raise StegoEngineError(f"Failed to read public key PEM: {exc}") from exc

    try:
        key = serialization.load_pem_public_key(pem_bytes)
    except (ValueError, TypeError) as exc:
        raise StegoEngineError(f"Failed to load public key: {exc}") from exc

    if not isinstance(key, rsa.RSAPublicKey):
        raise StegoEngineError("Loaded key is not an RSA public key.")
    return key


def rsa_encrypt_key(public_key: RSAPublicKey, key_bytes: bytes) -> bytes:
    """
    Encrypt a symmetric key using RSA-OAEP with SHA-256.

    :param public_key: RSA public key.
    :param key_bytes: Symmetric key bytes (e.g., 32 bytes for AES-256).
    :return: RSA-OAEP encrypted key bytes.
    """
    if not isinstance(key_bytes, (bytes, bytearray)):
        raise StegoEngineError("rsa_encrypt_key: key_bytes must be bytes-like.")

    try:
        ek = public_key.encrypt(
            key_bytes,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
    except ValueError as exc:
        raise StegoEngineError(f"RSA encryption failed: {exc}") from exc
    return ek


def rsa_decrypt_key(private_key: RSAPrivateKey, ek_bytes: bytes) -> bytes:
    """
    Decrypt a symmetric key encrypted with rsa_encrypt_key().

    :param private_key: RSA private key.
    :param ek_bytes: Encrypted key bytes.
    :return: Decrypted symmetric key bytes.
    :raises StegoEngineError: On decryption failure.
    """
    if not isinstance(ek_bytes, (bytes, bytearray)):
        raise StegoEngineError("rsa_decrypt_key: ek_bytes must be bytes-like.")

    try:
        key_bytes = private_key.decrypt(
            ek_bytes,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
    except ValueError as exc:
        raise StegoEngineError(
            "RSA decryption failed (wrong key or corrupted data)."
        ) from exc
    return key_bytes


def fingerprint_public_key(public_key: RSAPublicKey) -> str:
    """
    Compute a short fingerprint for the public key.

    Implementation: SHA-256 over DER encoding (SubjectPublicKeyInfo),
    returning the first 16 bytes as a 32-character hex string.

    :param public_key: RSA public key.
    :return: Hex fingerprint string (32 characters).
    """
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = hashlib.sha256(der).hexdigest()
    return digest[:32]


__all__ = [
    "RSAPrivateKey",
    "RSAPublicKey",
    "generate_rsa_keypair",
    "save_private_key_pem",
    "save_public_key_pem",
    "load_private_key_pem",
    "load_public_key_pem",
    "rsa_encrypt_key",
    "rsa_decrypt_key",
    "fingerprint_public_key",
]
