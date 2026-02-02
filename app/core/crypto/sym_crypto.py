from __future__ import annotations
import os
from typing import Optional, Tuple, Final

from argon2.low_level import hash_secret_raw, Type
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# ------------------------------------------------------------
# Argon2id – reasonable secure defaults (ตามแนว RFC 9106)
# ------------------------------------------------------------

# หน่วยของ MEMORY_COST = KiB
ARGON2_TIME_COST: Final[int] = 3        # รอบในการคำนวณ (t)
ARGON2_MEMORY_COST: Final[int] = 64_000 # 64 MiB (m) = 64 * 1024 KiB
ARGON2_PARALLELISM: Final[int] = 4      # ใช้ CPU threads (p)
ARGON2_HASH_LEN: Final[int] = 32        # 32 bytes = 256-bit key
ARGON2_SALT_LEN: Final[int] = 16        # อย่างน้อย 16 bytes

# ------------------------------------------------------------
# AES_GCM – reasonable secure defaults
# ------------------------------------------------------------
AESGCM_NONCE_LEN: Final[int] = 12       # Nonce 12 bytes (96-bit)


def generate_salt(length: int = ARGON2_SALT_LEN) -> bytes:
    """
    สร้าง salt แบบ cryptographically secure สำหรับ Argon2id
    """
    return os.urandom(length)


def derive_key_argon2id(
    password: str,
    salt: bytes,
    *,
    time_cost: int = ARGON2_TIME_COST,
    memory_cost: int = ARGON2_MEMORY_COST,
    parallelism: int = ARGON2_PARALLELISM,
    length: int = ARGON2_HASH_LEN,
) -> bytes:
    """
    Derive key จาก password ด้วย Argon2id และ PBKDF2(SHA-256)

    :param password: รหัสผ่านที่ผู้ใช้กรอก (string ปกติ)
    :param salt: ค่า salt แบบสุ่ม (os.urandom) ความยาว >= 16 bytes
    :param time_cost: จำนวนรอบการทำงาน (ยิ่งมากยิ่งช้า แต่ปลอดภัยขึ้น)
    :param memory_cost: หน่วยเป็น KiB, 64_000 = ~64 MiB
    :param parallelism: จำนวน thread/CPU lanes ที่ใช้
    :param length: ความยาว key ที่ต้องการ (bytes)
    :return: key สำหรับใช้กับ AES-GCM หรือ crypto อื่น ๆ (bytes)
    """
    if not isinstance(salt, (bytes, bytearray)):
        raise TypeError("salt ต้องเป็น bytes")

    password_bytes = password.encode("utf-8")

    key = hash_secret_raw(
        secret=password_bytes,
        salt=salt,
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
        hash_len=length,
        type=Type.ID,  # Argon2id (hybrid, ปลอดภัยต่อ GPU/side-channel)
    )
    return key

def derive_key_pbkdf2(
    password: str,
    salt: bytes,
    *,
    iterations: int = 200_000,
    length: int = 32,
) -> bytes:
    """
    PBKDF2-HMAC-SHA256 KDF.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(password.encode("utf-8"))

def aes_gcm_encrypt(
    key: bytes,
    plaintext: bytes,
    aad: Optional[bytes] = None,
) -> Tuple[bytes, bytes]:
    """
    AES-GCM encryption.

    Returns
    -------
    nonce, ciphertext_with_tag
    """
    aesgcm = AESGCM(key)
    nonce = os.urandom(AESGCM_NONCE_LEN)
    ct = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce, ct


def aes_gcm_decrypt(
    key: bytes,
    nonce: bytes,
    ciphertext: bytes,
    aad: Optional[bytes] = None,
) -> bytes:
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, aad)