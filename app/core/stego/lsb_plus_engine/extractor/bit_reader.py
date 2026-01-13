from __future__ import annotations

from typing import Tuple

from util import bitstream as bitutil
from util.header import decrypt_header, validate_header
from util.crypto import derive_key_pbkdf2, aes_gcm_decrypt
from util.exceptions import StegoEngineError

SALT_LEN = 16
HEADER_NONCE_LEN = 12
HEADER_CT_LEN = 9 + 16  # header plaintext 9 bytes + GCM tag 16


def parse_stream_plain(data: bytes, seed: str) -> bytes:
    """
    No AES mode:
      stream =SALT(16) +
          HEADER_NONCE(12) + HEADER_CT(9+16) + PAYLOAD(Length bytes)
    """
    # if len(data) < 9:
    #     raise StegoEngineError("Bitstream too short for header.")
    # header_plain = data[:9]
    # payload_len = validate_header(header_plain)
    # end = 9 + payload_len
    # if len(data) < end:
    #     raise StegoEngineError("Bitstream truncated (payload).")
    # return data[9:end]
    headerByte = SALT_LEN + HEADER_NONCE_LEN + HEADER_CT_LEN
    if len(data) < headerByte:
        raise StegoEngineError("Bitstream too short for AES header.")
    
    salt = data[:SALT_LEN]
    pos = SALT_LEN
    
    header_nonce = data[pos : pos + HEADER_NONCE_LEN]
    pos += HEADER_NONCE_LEN
    header_ct = data[pos : pos + HEADER_CT_LEN]
    pos += HEADER_CT_LEN
    
    key = derive_key_pbkdf2(seed, salt, length=32)

    header_plain = decrypt_header(header_ct, header_nonce, key)
    
    payload_len = validate_header(header_plain)
    
    end = headerByte + payload_len
    if len(data) < end:
        raise StegoEngineError("Bitstream truncated (payload).")
    return data[headerByte:end]


def parse_stream_aes(data: bytes, seed: str) -> bytes:
    """
    AES-hardened mode:
      stream =
          SALT(16) +
          HEADER_NONCE(12) + HEADER_CT(9+16) +
          PAYLOAD_NONCE(12) + PAYLOAD_CT(payload_len+16)
    """
    if len(data) < SALT_LEN + HEADER_NONCE_LEN + HEADER_CT_LEN:
        raise StegoEngineError("Bitstream too short for AES header.")

    salt = data[:SALT_LEN]
    pos = SALT_LEN

    header_nonce = data[pos : pos + HEADER_NONCE_LEN]
    pos += HEADER_NONCE_LEN
    header_ct = data[pos : pos + HEADER_CT_LEN]
    pos += HEADER_CT_LEN

    key = derive_key_pbkdf2(seed, salt, length=32)

    header_plain = decrypt_header(header_ct, header_nonce, key)

    payload_len = validate_header(header_plain)

    # payload: nonce + ciphertext(tag)
    if len(data) < pos + 12 + payload_len + 16:
        raise StegoEngineError("Bitstream truncated (payload AES).")

    payload_nonce = data[pos : pos + 12]
    pos += 12
    payload_ct = data[pos : pos + payload_len + 16]

    payload_plain = aes_gcm_decrypt(key, payload_nonce, payload_ct, aad=None)
    if len(payload_plain) != payload_len:
        # not fatal, but suspicious
        payload_plain = payload_plain[:payload_len]
    return payload_plain


def read_payload_from_bits(
    bits: list[int],
    aes_enabled: bool,
    seed: str,
) -> bytes:
    """
    Convert bitstream to bytes and parse according to mode.
    """
    data = bitutil.bits_to_bytes(bits)
    if aes_enabled:
        return parse_stream_aes(data, seed)
    else:
        return parse_stream_plain(data, seed)
