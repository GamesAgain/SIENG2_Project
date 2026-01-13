from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import numpy as np

from app.core.crypto.asym_crypto import fingerprint_public_key, load_public_key_pem, rsa_encrypt_key
from app.core.crypto.sym_crypto import aes_gcm_encrypt, derive_key_argon2id, generate_salt
from app.core.stego.lsb_plus_engine.analyzer.metrics import compute_psnr, compute_ssim, histogram_drift
from app.core.stego.lsb_plus_engine.analyzer.texture_map import compute_texture_features
from app.core.stego.lsb_plus_engine.embedder.capacity import compute_capacity
from app.core.stego.lsb_plus_engine.embedder.drift_control import BlockSafetyThresholds, is_block_safe
from app.core.stego.lsb_plus_engine.embedder.embedding import embed_in_lsb
from app.core.stego.lsb_plus_engine.embedder.noise_predictor import adjust_capacity_for_pixel
from app.core.stego.lsb_plus_engine.embedder.pixel_order import build_pixel_order
from app.core.stego.lsb_plus_engine.lsb_utils.bitstream import bytes_to_bits
from app.core.stego.lsb_plus_engine.lsb_utils.header import build_plain_header
from app.utils.exceptions import StegoEngineError
from app.utils.file_io import load_png




# byte value ที่จะ encode ลง stream เป็น mode
MODE_SYMMETRIC = 0x01
MODE_ASYMMETRIC = 0x02

SALT_LEN = 16
NONCE_LEN = 12  # AES-GCM nonce length (12 bytes)


@dataclass
class EmbedMetrics:
    psnr: float
    ssim: float
    hist_drift: float


class LSB_Plus:
     
    def embed(
        self,
        *,
        cover_path: str,
        payload_text: str,
        mode: str,
        password: Optional[str],
        public_key_path: Optional[str],
        show_progress: bool,
        # [เพิ่ม] รับฟังก์ชัน callback (รับ int, str) -> return None
        progress_callback: Optional[Callable[[int, str], None]] = None, 
    ) -> Tuple[np.ndarray, EmbedMetrics]:
        
        # --- Step 0: Start ---
        if progress_callback:
            progress_callback(5, "Loading resources...")

        # 1) Load cover PNG and payload
        cover = load_png(cover_path)    
        payload_bytes = payload_text.encode("utf-8")
        
        # --- Step 1: Texture Analysis ---
        if progress_callback:
            progress_callback(15, "Analyzing texture...")

        # 2) Analyze texture
        gray, grad_map, entropy_map, surface_map = compute_texture_features(cover)
        capacity_map = compute_capacity(surface_map)

        # --- Step 2: Encryption ---
        if progress_callback:
            progress_callback(30, "Encrypting payload...")

        # 3) เลือกโหมด + สร้าง byte stream
        mode_str = (mode or "").strip().lower()
        if mode_str not in ("password", "public"):
            raise StegoEngineError("mode must be 'password' or 'public'.")

        if mode_str == "password":
            if not isinstance(password, str) or password.strip() == "":
                raise StegoEngineError("password must be non-empty in symmetric mode.")

            stream = self._build_symmetric_stream(
                password=password,
                payload_bytes=payload_bytes,
            )
            seed_for_order = password

        else:
            if not isinstance(public_key_path, str) or not public_key_path.strip():
                raise StegoEngineError("Public-key mode requires a valid public_key_path.")

            stream, fingerprint = self._build_asymmetric_stream(
                public_key_path=public_key_path,
                payload_bytes=payload_bytes,
            )
            seed_for_order = f"asym:{fingerprint}"

        # --- Step 3: Preparing Embedding ---
        if progress_callback:
            progress_callback(50, "Preparing pixel order...")

        # 4) Build pixel order
        order = build_pixel_order(entropy_map, seed_for_order)

        # 5) Convert stream to bits
        bits = bytes_to_bits(stream)

        # 6) Prepare block map & arrays
        h, w, _ = cover.shape
        num_pixels = h * w
        flat_capacity = capacity_map.reshape(-1)

        block_rows = (h + 7) // 8
        block_cols = (w + 7) // 8
        block_map = np.zeros(num_pixels, dtype=np.int32)
        for idx in range(num_pixels):
            yy = idx // w
            xx = idx % w
            br = yy // 8
            bc = xx // 8
            block_map[idx] = br * block_cols + bc

        num_blocks = block_rows * block_cols
        block_done = np.zeros(num_blocks, dtype=bool)

        block_pixel_positions: dict[int, list[int]] = {}
        for pos, flat_idx in enumerate(order):
            b_id = int(block_map[int(flat_idx)])
            block_pixel_positions.setdefault(b_id, []).append(pos)

        # --- Step 4: Embedding ---
        if progress_callback:
            progress_callback(70, "Embedding data into pixels...")

        # 7) Embedding
        thresholds = BlockSafetyThresholds()
        gray_for_coords = gray

        def adjust_cap(gray_img, y, x, req_bits):
            return adjust_capacity_for_pixel(gray_img, y, x, req_bits)

        def block_checker(orig_block, stego_block):
            return is_block_safe(orig_block, stego_block, thresholds)

        stego = cover.copy()
        embed_fn = embed_in_lsb

        stego = embed_fn(
            stego,
            order,
            flat_capacity,
            bits,
            block_map,
            block_done,
            block_pixel_positions,
            gray_for_coords,
            adjust_cap,
            block_checker,
        )

        # --- Step 5: Verification ---
        if progress_callback:
            progress_callback(90, "Verifying quality metrics...")

        # 8) Quality metrics
        psnr_val = compute_psnr(cover, stego)
        ssim_val = compute_ssim(cover, stego)
        hist_drift_val = histogram_drift(cover, stego)

        if psnr_val < 48.0 or ssim_val < 0.985:
            raise StegoEngineError(
                f"Output quality below thresholds:\n"
                f"PSNR={psnr_val:.2f} dB (>=48 required), "
                f"SSIM={ssim_val:.4f} (>=0.985 required)"
            )

        metrics = EmbedMetrics(psnr=psnr_val, ssim=ssim_val, hist_drift=hist_drift_val)
        
        # --- Finished ---
        if progress_callback:
            progress_callback(100, "Completed Successfully!")

        return stego, metrics

    # ------------------------------------------------------------------ stream builders

    def _build_symmetric_stream(
        self,
        *,
        password: str,
        payload_bytes: bytes,
    ) -> bytes:
        """
        สร้าง byte stream สำหรับ Symmetric mode (Password + Argon2id + AES-GCM)

        Layout:

            [ MODE         ] 1 byte  = 0x01
            [ HEADER       ] 7 bytes = STG + LEN(ciphertext)
            [ SALT         ] 16 bytes
            [ NONCE        ] 12 bytes
            [ CIPHERTEXT   ] LEN bytes
        """
        if not password:
            raise StegoEngineError("Symmetric mode requires a non-empty password.")

        # 1) Salt + KDF
        salt = generate_salt()  # 16 bytes โดย default
        key = derive_key_argon2id(password, salt)

        # 2) Encrypt payload
        nonce, ciphertext = aes_gcm_encrypt(key, payload_bytes, aad=None)

        # 3) Header (plaintext STG + LEN(ciphertext))
        header_bytes = build_plain_header(len(ciphertext))

        # 4) Encode mode byte
        mode_byte = bytes([MODE_SYMMETRIC])

        stream = b"".join(
            [
                mode_byte,
                header_bytes,
                salt,
                nonce,
                ciphertext,
            ]
        )
        return stream

    def _build_asymmetric_stream(
        self,
        *,
        public_key_path: str,
        payload_bytes: bytes,
    ) -> Tuple[bytes, str]:
        """
        สร้าง stream สำหรับ Asymmetric Mode (Hybrid RSA + AES-GCM):

        Layout:

            [ MODE          ] 1 byte = 0x02
            [ HEADER        ] 7 bytes = "STG" + LEN(ciphertext)
            [ EK_LEN        ] 2 bytes (uint16) = ความยาวของ rsa_encrypted_key
            [ EK            ] EK_LEN bytes (RSA-OAEP encrypted AES key)
            [ NONCE         ] 12 bytes
            [ CIPHERTEXT    ] LEN bytes

        Return:
            (stream_bytes, public_key_fingerprint_hex)
        """

        # 1) Load public key
        try:
            public_key = load_public_key_pem(public_key_path)
        except Exception as exc:
            raise StegoEngineError(f"Failed to load public key: {exc}") from exc

        # 2) Generate AES-256 symmetric key (random 32 bytes)
        sym_key = generate_salt(32)  # ใช้ generate_salt เป็น random 32 bytes

        # 3) Encrypt symmetric key with RSA-OAEP
        try:
            ek = rsa_encrypt_key(public_key, sym_key)
            print(f'ek{ek}')
        except Exception as exc:
            raise StegoEngineError(f"RSA encryption failed: {exc}") from exc

        ek_len = len(ek)
        if ek_len > 65535:
            raise StegoEngineError(
                "RSA encrypted key is too large for uint16 length field."
            )

        # 4) Encrypt payload via AES-GCM
        nonce, ciphertext = aes_gcm_encrypt(sym_key, payload_bytes, aad=None)
        print(f'ciphertext{ciphertext}')
        # 5) Build header STG + LEN(ciphertext)
        header = build_plain_header(len(ciphertext))

        # 6) Pack stream
        stream = b"".join(
            [
                bytes([MODE_ASYMMETRIC]),
                header,
                ek_len.to_bytes(2, "big"),
                ek,
                nonce,
                ciphertext,
            ]
        )

        # fingerprint (ใช้เป็น seed ของ pixel order)
        fingerprint = fingerprint_public_key(public_key)
        return stream, fingerprint