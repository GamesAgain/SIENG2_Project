from __future__ import annotations

from app.core.crypto.sym_crypto import aes_gcm_encrypt
from app.utils.exceptions import StegoEngineError


"""
Header utilities for Adaptive Steganography Engine v3.

PLAINTEXT HEADER LAYOUT (7 bytes total, same for all modes):

    [ MAGIC (3 bytes) ]  = b"STG"
    [ LEN   (4 bytes) ]  = uint32 big-endian, payload length in bytes  จุค่าความยาวได้ตั้งแต่ 0 - 4,294,967,295 bytes (~4GB)

- ไม่เก็บ MODE ใน header (MODE เป็น byte แรกของ stream แยกต่างหาก)
- header ทั้งก้อนอาจถูก AES-GCM เข้ารหัสต่อใน layer ถัดไป (sym/asym)

ฟังก์ชันในไฟล์นี้มีขอบเขตแค่:
- สร้าง plaintext header จาก payload_length
- ตรวจสอบและดึง payload_length จาก plaintext header

"""

from typing import Final, Tuple



# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

MAGIC: Final[bytes] = b"STG"            # 3-byte magic
MAGIC_LEN: Final[int] = len(MAGIC)      # 3

LEN_LEN: Final[int] = 4                 # 4-byte uint32 (big-endian)
HEADER_LEN: Final[int] = MAGIC_LEN + LEN_LEN  # 7 bytes

# payload_len เก็บใน 4 bytes unsigned -> 0 .. 2^32 - 1
MAX_PAYLOAD_LEN: Final[int] = (1 << (LEN_LEN * 8)) - 1


# ---------------------------------------------------------------------------
# BUILD
# ---------------------------------------------------------------------------

def build_plain_header(payload_length: int) -> bytes:
    """
    สร้าง PLAINTEXT HEADER v3:

        MAGIC (3 bytes) + PAYLOAD_LEN (4 bytes big-endian)

    Parameters
    ----------
    payload_length : int
        ความยาว payload (จำนวน byte) ก่อนเข้ารหัส/ฝัง

    Returns
    -------
    header : bytes
        ความยาว 7 bytes เสมอ

    Raises
    ------
    StegoEngineError
        ถ้า payload_length อยู่นอกช่วง 0..2^32-1
    """
    if not isinstance(payload_length, int):
        raise StegoEngineError("payload_length must be an integer.")

    if payload_length < 0:
        raise StegoEngineError("payload_length must be non-negative.")

    if payload_length > MAX_PAYLOAD_LEN:
        raise StegoEngineError(
            f"payload_length too large for 4-byte uint32: {payload_length}"
        )

    length_bytes = payload_length.to_bytes(LEN_LEN, "big", signed=False)
    return MAGIC + length_bytes


# ---------------------------------------------------------------------------
# ENCRYPTION / PARSE
# ---------------------------------------------------------------------------

def encrypt_header(plain_header: bytes, key: bytes) -> Tuple[bytes, bytes]:
    """
    Encrypt header with AES-GCM.

    Returns
    -------
    nonce, ciphertext_with_tag
    """
    if len(plain_header) != MAGIC_LEN + LEN_LEN:
        raise ValueError("Header must be exactly 9 bytes.")
    nonce, ct = aes_gcm_encrypt(key, plain_header)
    
    return nonce, ct


# def decrypt_header(ciphertext: bytes, nonce: bytes, key: bytes) -> bytes:
#     aesgcm = aes_gcm_decrypt()
#     return aesgcm.decrypt(nonce, ciphertext, None)


# ---------------------------------------------------------------------------
# VALIDATE / PARSE
# ---------------------------------------------------------------------------

def validate_header(plain_header: bytes) -> int:
    """
    ตรวจสอบ PLAINTEXT HEADER v3 และคืนค่า payload_length

    Expected layout (7 bytes):

        MAGIC (3) | LEN (4)

    Parameters
    ----------
    plain_header : bytes
        header ที่ได้หลังจาก decrypt แล้ว (ถ้ามีการเข้ารหัส header)

    Returns
    -------
    payload_length : int

    Raises
    ------
    StegoEngineError
        - ถ้า header length ไม่ใช่ 7 bytes
        - ถ้า MAGIC ไม่ตรง b"STG"
    """
    if len(plain_header) != HEADER_LEN:
        raise StegoEngineError(
            f"Header must be {HEADER_LEN} bytes, got {len(plain_header)}"
        )

    # เช็ค MAGIC แบบ slice ตรง ๆ เร็วและชัดเจน
    if plain_header[:MAGIC_LEN] != MAGIC:
        raise StegoEngineError("Invalid header magic (expected b'STG').")

    # 4 bytes สุดท้ายคือ payload length (uint32 big-endian)
    length_bytes = plain_header[MAGIC_LEN:]
    payload_len = int.from_bytes(length_bytes, "big", signed=False)

    return payload_len
