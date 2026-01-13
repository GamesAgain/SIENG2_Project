from __future__ import annotations

from typing import Optional

import numpy as np

from analyzer.texture_map import compute_texture_features
from embedder.capacity import compute_capacity
from embedder.pixel_order import build_pixel_order
from extractor.extraction import extract_bits_low_level
from util import bitstream as bitutil
from util.header import validate_header, HEADER_LEN
from util.image_io import load_png
from util.exceptions import StegoEngineError

from crypto.sym_crypto import (
    derive_key_argon2id,
    aes_gcm_decrypt,
)
from crypto.asym_crypto import (
    load_private_key_pem,
    rsa_decrypt_key,
    fingerprint_public_key,
)

MODE_SYMMETRIC = 0x01
MODE_ASYMMETRIC = 0x02

SALT_LEN = 16
NONCE_LEN = 12
EK_LEN_LEN = 2  # เก็บ ek_len เป็น uint16


class ExtractController:
    """
    High-level orchestrator for extraction pipeline (v3).

    รองรับ:
      - Symmetric / password mode
      - Asymmetric / public-key mode
    """

    def extract_to_text(
        self,
        stego_path: str,
        *,
        mode: str,
        password: Optional[str] = None,
        private_key_path: Optional[str] = None,
        show_progress: bool = False,
    ) -> str:
        """
        API หลักให้ GUI เรียกใช้ (จาก ExtractTab)

        Parameters
        ----------
        stego_path : str
            path ของ stego PNG
        mode : str
            "password" หรือ "public"
        password : Optional[str]
            - ถ้า mode == "password"  -> symmetric password
            - ถ้า mode == "public"    -> password ของไฟล์ private key (ถ้ามี)
        private_key_path : Optional[str]
            ใช้เมื่อ mode == "public"
        show_progress : bool
            เผื่อใช้ progress ในอนาคต
        """
        payload_bytes = self._extract_bytes(
            stego_path=stego_path,
            mode=mode,
            password=password,
            private_key_path=private_key_path,
            show_progress=show_progress,
        )

        try:
            return payload_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StegoEngineError(
                "Failed to decode payload as UTF-8. "
                "Wrong password/private key or corrupted stego?"
            ) from exc

    # ------------------------------------------------------------------ internal

    def _extract_bytes(
        self,
        *,
        stego_path: str,
        mode: str,
        password: Optional[str],
        private_key_path: Optional[str],
        show_progress: bool,
    ) -> bytes:
        # 1) Load stego
        stego = load_png(stego_path)

        # 2) Recompute analysis (ให้ match ฝั่ง embed)
        gray, grad_map, entropy_map, surface_map = compute_texture_features(stego)
        capacity_map = compute_capacity(surface_map)

        # 3) Build pixel order – ต้องใช้ seed เดียวกันกับ embed
        mode_str = (mode or "").strip().lower()
        if mode_str not in ("password", "public"):
            raise StegoEngineError("mode must be 'password' or 'public'.")

        if mode_str == "password":
            if not isinstance(password, str) or password.strip() == "":
                raise StegoEngineError("Password mode requires a non-empty password.")
            seed_for_order = password
        else:
            # Asymmetric: ใช้ fingerprint ของ public key เป็น seed
            if not isinstance(private_key_path, str) or private_key_path.strip() == "":
                raise StegoEngineError(
                    "Public-key mode requires a private key PEM path."
                )

            try:
                # ใช้ password ที่ GUI ส่งมาเป็น private-key password
                priv_key = load_private_key_pem(
                    private_key_path,
                    password=password or None,
                )
            except Exception as exc:
                raise StegoEngineError(
                    f"Failed to load private key (wrong password or invalid PEM): {exc}"
                ) from exc

            pub_key = priv_key.public_key()
            fp = fingerprint_public_key(pub_key)
            seed_for_order = f"asym:{fp}"

        order = build_pixel_order(entropy_map, seed_for_order)

        # 4) Extract bits
        flat_capacity = capacity_map.reshape(-1)
        bits = extract_bits_low_level(stego, order, flat_capacity)

        # 5) bits -> bytes
        stream_bytes = bitutil.bits_to_bytes(bits)
        if not stream_bytes:
            raise StegoEngineError("Extracted bitstream is empty – no data found.")

        # 6) MODE byte
        mode_value = stream_bytes[0]
        if mode_value not in (MODE_SYMMETRIC, MODE_ASYMMETRIC):
            raise StegoEngineError(f"Unknown byte in stego stream")

        # cross-check
        if mode_str == "password" and mode_value != MODE_SYMMETRIC:
            raise StegoEngineError(
                "Stego data is not in password mode (mode byte mismatch)."
            )
        if mode_str == "public" and mode_value != MODE_ASYMMETRIC:
            raise StegoEngineError(
                "Stego data is not in public-key mode (mode byte mismatch)."
            )

        # 7) แตกตาม mode
        if mode_value == MODE_SYMMETRIC:
            return self._decrypt_symmetric_stream(
                stream_bytes=stream_bytes,
                password=password or "",
            )
        else:
            return self._decrypt_asymmetric_stream(
                stream_bytes=stream_bytes,
                private_key_path=private_key_path or "",
                private_key_password=password,  # <- ส่ง password ของไฟล์ key มาด้วย
            )

    # ------------------------------------------------------------------ symmetric

    def _decrypt_symmetric_stream(self, *, stream_bytes: bytes, password: str) -> bytes:
        if not password:
            raise StegoEngineError("Password is required for symmetric decryption.")

        # ต้องมีอย่างน้อย MODE + HEADER + SALT + NONCE
        min_len = 1 + HEADER_LEN + SALT_LEN + NONCE_LEN
        if len(stream_bytes) < min_len:
            raise StegoEngineError(
                f"Stego stream too short for symmetric layout (got {len(stream_bytes)} bytes)."
            )

        # MODE | HEADER | SALT | NONCE | REST
        mode_b, header_bytes, salt, nonce, rest = bitutil.unpack_bitstream(
            stream_bytes,
            [1, HEADER_LEN, SALT_LEN, NONCE_LEN],
        )

        mode_value = mode_b[0]
        if mode_value != MODE_SYMMETRIC:
            raise StegoEngineError(
                f"_decrypt_symmetric_stream called with wrong mode byte: {mode_value:#02x}"
            )

        ciphertext_len = validate_header(header_bytes)
        if ciphertext_len < 0:
            raise StegoEngineError("Negative ciphertext length in header (invalid).")

        if len(rest) < ciphertext_len:
            raise StegoEngineError(
                f"Ciphertext truncated: expected {ciphertext_len} bytes, got {len(rest)}"
            )

        ciphertext = rest[:ciphertext_len]

        key = derive_key_argon2id(password, salt)

        try:
            plaintext = aes_gcm_decrypt(key, nonce, ciphertext, aad=None)
        except Exception as exc:
            raise StegoEngineError(
                "AES-GCM decryption failed. Wrong password or corrupted data."
            ) from exc

        return plaintext

    # ------------------------------------------------------------------ asymmetric

    def _decrypt_asymmetric_stream(
        self,
        *,
        stream_bytes: bytes,
        private_key_path: str,
        private_key_password: Optional[str],
    ) -> bytes:
        if not private_key_path:
            raise StegoEngineError("Private key path is required for asymmetric mode.")

        # ขั้นแรก: MODE | HEADER | EK_LEN | REST1
        min_len = 1 + HEADER_LEN + EK_LEN_LEN + NONCE_LEN
        if len(stream_bytes) < min_len:
            raise StegoEngineError(
                f"Stego stream too short for asymmetric layout (got {len(stream_bytes)} bytes)."
            )

        mode_b, header_bytes, ek_len_bytes, rest1 = bitutil.unpack_bitstream(
            stream_bytes,
            [1, HEADER_LEN, EK_LEN_LEN],
        )
        mode_value = mode_b[0]
        if mode_value != MODE_ASYMMETRIC:
            raise StegoEngineError(
                f"_decrypt_asymmetric_stream called with wrong mode byte: {mode_value:#02x}"
            )

        ek_len = int.from_bytes(ek_len_bytes, "big", signed=False)
        if ek_len <= 0:
            raise StegoEngineError(f"Invalid encrypted-key length: {ek_len}")

        if len(rest1) < ek_len + NONCE_LEN:
            raise StegoEngineError(
                "Stego stream truncated before ENC_KEY + NONCE."
            )

        # ENC_KEY | NONCE | REST2
        enc_key, nonce, rest2 = bitutil.unpack_bitstream(
            rest1,
            [ek_len, NONCE_LEN],
        )

        ciphertext_len = validate_header(header_bytes)
        if ciphertext_len < 0:
            raise StegoEngineError("Negative ciphertext length in header (invalid).")

        if len(rest2) < ciphertext_len:
            raise StegoEngineError(
                f"Ciphertext truncated: expected {ciphertext_len} bytes, got {len(rest2)}"
            )

        ciphertext = rest2[:ciphertext_len]

        # Load private key (ใช้ password ถ้ามี)
        try:
            priv_key = load_private_key_pem(
                private_key_path,
                password=private_key_password or None,
            )
        except Exception as exc:
            raise StegoEngineError(
                f"Failed to load private key (wrong password or invalid PEM): {exc}"
            ) from exc

        # Decrypt symmetric key
        try:
            sym_key = rsa_decrypt_key(priv_key, enc_key)
        except Exception as exc:
            raise StegoEngineError(
                "RSA decryption of symmetric key failed. Wrong private key or corrupted data."
            ) from exc

        # Decrypt payload
        try:
            plaintext = aes_gcm_decrypt(sym_key, nonce, ciphertext, aad=None)
        except Exception as exc:
            raise StegoEngineError(
                "AES-GCM decryption (asymmetric mode) failed. Data may be corrupted."
            ) from exc

        return plaintext
