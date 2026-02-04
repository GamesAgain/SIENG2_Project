from dataclasses import dataclass
import os
from typing import Callable, Optional, Tuple

import numpy as np
from PIL import Image

# --- Crypto Imports ---
from app.core.crypto.asym_crypto import (
    fingerprint_public_key, 
    load_public_key_pem, 
    rsa_encrypt_key,
    load_private_key_pem,   # [Added] สำหรับ Extract Asym
    rsa_decrypt_key         # [Added] สำหรับ Extract Asym
)
from app.core.crypto.sym_crypto import (
    aes_gcm_encrypt, 
    derive_key_argon2id, 
    generate_salt,
    aes_gcm_decrypt         # [Added] สำหรับ Extract Sym
)

# --- Engine Imports ---
from app.core.stego.lsb_plus.engine.analyzer.capacity import compute_capacity
from app.core.stego.lsb_plus.engine.analyzer.texture_map import compute_texture_features
import app.core.stego.lsb_plus.engine.util.bitstream as bitutil
from app.core.stego.lsb_plus.engine.drift_control import BlockSafetyThresholds, is_block_safe
from app.core.stego.lsb_plus.engine.embedding import embed_bits_low_level
from app.core.stego.lsb_plus.engine.extraction import extract_bits_low_level # [Added] ฟังก์ชันถอดรหัสระดับล่าง
from app.core.stego.lsb_plus.engine.util.header import build_plain_header, validate_header, HEADER_LEN
from app.core.stego.lsb_plus.engine.util.metrics import compute_psnr, compute_ssim, histogram_drift
from app.core.stego.lsb_plus.engine.noise_predictor import adjust_capacity_for_pixel
from app.core.stego.lsb_plus.engine.pixel_order import build_pixel_order

# --- Constants ---
MODE_NONE = 0x00 
MODE_SYMMETRIC = 0x01
MODE_ASYMMETRIC = 0x02

SALT_LEN = 16
NONCE_LEN = 12
EK_LEN_LEN = 2 

@dataclass
class EmbedMetrics:
    psnr: float
    ssim: float
    hist_drift: float

class LSBPP:
    # =========================================================================
    # 1. EMBEDDING (Optimized & Vectorized)
    # =========================================================================
    def embed(
        self,
        cover_path: str,
        payload_text: str,
        *,
        encrypt_mode: str,
        password: Optional[str] = None,
        public_key_path: Optional[str] = None,
        status_callback: Optional[Callable[[str, int], None]] = None
    ):
        def update(text, percent):
            if status_callback: status_callback(text, percent)
        
        # 1) Load & Prep
        update("Loading cover image...", 5)
        cover = self.load_png(cover_path)    
        payload_bytes = payload_text.encode("utf-8")
        
        # 2) Analyze Texture
        update("Analyzing image texture & capacity...", 15)
        gray, _, entropy_map, surface_map = compute_texture_features(cover)
        
        update("Calculating embedding capacity...", 20)
        capacity_map = compute_capacity(surface_map)
        
        # 3) Build Stream & Seed
        update("Encrypting payload & building stream...", 30)
        mode_str = (encrypt_mode or "").strip().lower()
        allowed_modes = ("password", "public", "none")
        if mode_str not in allowed_modes:
            raise Exception(f"Mode must be one of: {allowed_modes}")
        
        if mode_str == "password":
            if not password: raise ValueError("Password cannot be empty.")
            stream = self._build_symmetric_stream(password=password, payload_bytes=payload_bytes)
            seed_for_order = password # Symmetric Seed = Password
            
        elif mode_str == "public":
            if not public_key_path: raise ValueError("Public-key mode requires path.")
            stream, fingerprint = self._build_asymmetric_stream(public_key_path=public_key_path, payload_bytes=payload_bytes)
            seed_for_order = f"asym:{fingerprint}" # Asymmetric Seed = Fingerprint
            
        else: # none
            header_bytes = build_plain_header(len(payload_bytes))
            stream = b"".join([bytes([MODE_NONE]), header_bytes, payload_bytes])
            seed_for_order = "default_seed"
            
        # 4) Pixel Order
        update("Generating secure pixel order...", 45)
        order = build_pixel_order(entropy_map, seed_for_order)
        
        # 5) Bits Conversion
        update("Converting to bitstream...", 50)
        bits = bitutil.bytes_to_bits(stream)
        
        # 6) Block Optimization (Vectorized Broadcasting)
        update("Preparing block optimization maps...", 60)
        h, w = cover.shape[:2]
        num_pixels = h * w
        block_cols = (w + 7) // 8
        
        # [Optimize] Broadcasting คำนวณ Block Map ทีเดียวทั้งภาพ
        row_indices = np.arange(h, dtype=np.int32) // 8
        col_indices = np.arange(w, dtype=np.int32) // 8
        block_map = (row_indices[:, None] * block_cols + col_indices[None, :]).ravel()

        # [Optimize] Grouping
        pixel_block_ids = block_map[order]
        sort_idx = np.argsort(pixel_block_ids)
        sorted_blocks = pixel_block_ids[sort_idx]
        diff_idx = np.where(np.diff(sorted_blocks) != 0)[0] + 1
        split_positions = np.split(sort_idx, diff_idx)
        unique_block_ids = sorted_blocks[np.insert(diff_idx, 0, 0)]
        block_pixel_positions = dict(zip(unique_block_ids, split_positions))
        
        # 7) Embedding (JIT Loop)
        update("Embedding data into pixels...", 70)
        thresholds = BlockSafetyThresholds()
        
        stego = embed_bits_low_level(
            cover.copy(),
            order,
            capacity_map.ravel(),
            bits,
            block_map,
            np.zeros(len(unique_block_ids) + 100, dtype=bool), # block_done buffer
            block_pixel_positions,
            gray,
            adjust_capacity_for_pixel,
            lambda o, s: is_block_safe(o, s, thresholds),
        )
         
        # 8) Metrics
        update("Calculating quality metrics...", 95)
        metrics = EmbedMetrics(
            psnr=compute_psnr(cover, stego),
            ssim=compute_ssim(cover, stego),
            hist_drift=histogram_drift(cover, stego)
        )
        update("Done.", 100)
        return stego, metrics

    # =========================================================================
    # 2. EXTRACTION (Added & Logic-Matched)
    # =========================================================================
    def extract(
        self,
        stego_path: str,
        *,
        encrypt_mode: str,
        password: Optional[str] = None,
        private_key_path: Optional[str] = None,
        status_callback: Optional[Callable[[str, int], None]] = None
    ) -> str:
        """
        Extract hidden payload.
        Steps: Load -> Analyze -> Reconstruct Seed -> Extract Bits -> Decrypt.
        """
        def update(text, percent):
            if status_callback: status_callback(text, percent)

        # 1) Load Stego
        update("Loading stego image...", 5)
        stego = self.load_png(stego_path)

        # 2) Recompute Analysis (MUST match Embed exactly)
        update("Analyzing texture & capacity...", 15)
        gray, _, entropy_map, surface_map = compute_texture_features(stego)
        capacity_map = compute_capacity(surface_map)

        # 3) Determine Seed (CRITICAL FIX: Match Embed Logic)
        update("Reconstructing pixel order...", 30)
        mode_str = (encrypt_mode or "").strip().lower()
        seed_for_order = None

        if mode_str == "password":
            if not password: raise ValueError("Password required for extraction.")
            seed_for_order = password # Seed = Password
            
        elif mode_str == "public":
            if not private_key_path: raise ValueError("Private key path required.")
            try:
                # [Fix] Derive Fingerprint from Private Key -> Public Key
                priv_key = load_private_key_pem(private_key_path, password=password)
                pub_key = priv_key.public_key()
                fp = fingerprint_public_key(pub_key)
                seed_for_order = f"asym:{fp}" # Seed = asym:Fingerprint
            except Exception as e:
                raise Exception(f"Key Error: {e}")
        
        elif mode_str == "none":
            seed_for_order = "default_seed"
        else:
            raise ValueError(f"Unknown mode: {mode_str}")

        # 4) Build Order & Extract
        update("Extracting raw bits...", 50)
        order = build_pixel_order(entropy_map, seed_for_order)
        bits = extract_bits_low_level(stego, order, capacity_map.ravel()) # เรียก engine
        
        # 5) Bits -> Bytes
        update("Parsing bitstream...", 70)
        stream_bytes = bitutil.bits_to_bytes(bits)
        if not stream_bytes: raise Exception("No hidden data found (empty stream).")

        # 6) Check Mode Byte
        mode_byte = stream_bytes[0]
        
        # 7) Decrypt per Mode
        update("Decrypting payload...", 80)
        try:
            if mode_byte == MODE_SYMMETRIC:
                if mode_str != "password": raise Exception("Mode mismatch: Found Symmetric data.")
                payload_bytes = self._decrypt_symmetric_stream(stream_bytes, password or "")
                
            elif mode_byte == MODE_ASYMMETRIC:
                if mode_str != "public": raise Exception("Mode mismatch: Found Asymmetric data.")
                payload_bytes = self._decrypt_asymmetric_stream(stream_bytes, private_key_path, password)
                
            elif mode_byte == MODE_NONE:
                payload_bytes = self._decrypt_plain_stream(stream_bytes)
                
            else:
                raise Exception(f"Unknown/Corrupted mode byte: {mode_byte}")
                
        except Exception as e:
            raise Exception(f"Decryption Error: {str(e)}")

        update("Done.", 100)
        return payload_bytes.decode("utf-8")

    # =========================================================================
    # 3. HELPERS (Stream Builders & Decrypters)
    # =========================================================================
    def _build_symmetric_stream(self, *, password: str, payload_bytes: bytes) -> bytes:
        salt = generate_salt()
        key = derive_key_argon2id(password, salt)
        nonce, ciphertext = aes_gcm_encrypt(key, payload_bytes)
        header = build_plain_header(len(ciphertext))
        return b"".join([bytes([MODE_SYMMETRIC]), header, salt, nonce, ciphertext])
    
    def _decrypt_symmetric_stream(self, stream_bytes, password):
        # [MODE] [HEADER] [SALT] [NONCE] [CT]
        idx = 1
        header = stream_bytes[idx : idx + HEADER_LEN]; idx += HEADER_LEN
        c_len = validate_header(header)
        salt = stream_bytes[idx : idx + SALT_LEN]; idx += SALT_LEN
        nonce = stream_bytes[idx : idx + NONCE_LEN]; idx += NONCE_LEN
        
        if len(stream_bytes) < idx + c_len: raise Exception("Ciphertext truncated.")
        ct = stream_bytes[idx : idx + c_len]
        
        key = derive_key_argon2id(password, salt)
        return aes_gcm_decrypt(key, nonce, ct)

    def _build_asymmetric_stream(self, *, public_key_path: str, payload_bytes: bytes) -> Tuple[bytes, str]:
        pub_key = load_public_key_pem(public_key_path)
        sym_key = generate_salt(32)
        ek = rsa_encrypt_key(pub_key, sym_key)
        nonce, ct = aes_gcm_encrypt(sym_key, payload_bytes)
        header = build_plain_header(len(ct))
        
        stream = b"".join([
            bytes([MODE_ASYMMETRIC]), header, 
            len(ek).to_bytes(2, "big"), ek, 
            nonce, ct
        ])
        return stream, fingerprint_public_key(pub_key)

    def _decrypt_asymmetric_stream(self, stream_bytes, priv_path, priv_pwd):
        # [MODE] [HEADER] [EK_LEN] [EK] [NONCE] [CT]
        idx = 1
        header = stream_bytes[idx : idx + HEADER_LEN]; idx += HEADER_LEN
        c_len = validate_header(header)
        ek_len = int.from_bytes(stream_bytes[idx : idx + 2], "big"); idx += 2
        ek = stream_bytes[idx : idx + ek_len]; idx += ek_len
        nonce = stream_bytes[idx : idx + NONCE_LEN]; idx += NONCE_LEN
        
        if len(stream_bytes) < idx + c_len: raise Exception("Ciphertext truncated.")
        ct = stream_bytes[idx : idx + c_len]
        
        priv_key = load_private_key_pem(priv_path, password=priv_pwd)
        sym_key = rsa_decrypt_key(priv_key, ek)
        return aes_gcm_decrypt(sym_key, nonce, ct)

    def _decrypt_plain_stream(self, stream_bytes):
        idx = 1
        header = stream_bytes[idx : idx + HEADER_LEN]; idx += HEADER_LEN
        p_len = validate_header(header)
        return stream_bytes[idx : idx + p_len]

    def load_png(self, path: str) -> np.ndarray:
        if not os.path.isfile(path): raise Exception(f"File not found: {path}")
        with Image.open(path) as img:
            self._validate_png_image(img, path)
            return np.asarray(img.convert("RGB"), dtype=np.uint8)
    
    def _validate_png_image(self, img: Image.Image, path: str) -> None:
        if img.format != "PNG": raise Exception(f"File is not PNG: {path}")
        if img.mode not in ("RGB", "RGBA", "P", "L"):
            raise Exception(f"Invalid PNG mode: {img.mode}")