from dataclasses import dataclass
import os
from typing import Optional, Tuple

import numpy as np
from PIL import Image

from app.core.crypto.asym_crypto import fingerprint_public_key, load_public_key_pem, rsa_encrypt_key
from app.core.crypto.sym_crypto import aes_gcm_encrypt, derive_key_argon2id, generate_salt
from app.core.stego.lsb_plus.engine.analyzer.capacity import compute_capacity
from app.core.stego.lsb_plus.engine.analyzer.texture_map import compute_texture_features
import app.core.stego.lsb_plus.engine.util.bitstream as bitutil
from app.core.stego.lsb_plus.engine.drift_control import BlockSafetyThresholds, is_block_safe
from app.core.stego.lsb_plus.engine.embedding import embed_bits_low_level
from app.core.stego.lsb_plus.engine.util.header import build_plain_header
from app.core.stego.lsb_plus.engine.util.metrics import compute_psnr, compute_ssim, histogram_drift
from app.core.stego.lsb_plus.engine.noise_predictor import adjust_capacity_for_pixel
from app.core.stego.lsb_plus.engine.pixel_order import build_pixel_order

# byte value ที่จะ encode ลง stream เป็น mode
MODE_NONE = 0x00 
MODE_SYMMETRIC = 0x01
MODE_ASYMMETRIC = 0x02

@dataclass
class EmbedMetrics:
    psnr: float
    ssim: float
    hist_drift: float

SALT_LEN = 16
NONCE_LEN = 12  # AES-GCM nonce length (12 bytes)

class LSBPP:
    def embed(
        self,
        cover_path: str,
        payload_text: str,
        *,
        encrypt_mode: str,
        password: Optional[str] = None,
        public_key_path: Optional[str] = None,
    ):
        
        # 1) Load cover PNG and prepare payload to byte
        cover = self.load_png(cover_path)    
        payload_bytes = payload_text.encode("utf-8")
        
        # 2) Analyze texture
        gray, grad_map, entropy_map, surface_map = compute_texture_features(cover)
        capacity_map = compute_capacity(surface_map)
        
        # 3) เลือกโหมด + สร้าง byte stream ตาม mode + seed สำหรับ pixel order
        mode_str = (encrypt_mode or "").strip().lower()
        allowed_modes = ("password", "public", "none")
        if mode_str not in allowed_modes:
            raise Exception(f"Mode must be one of: {allowed_modes}")
        
        # --- CASE 1: Password (Symmetric AES) ---
        if mode_str == "password":
            if not isinstance(password, str) or not password.strip():
                raise ValueError("Password cannot be empty.")

            # สร้าง Stream ด้วย AES
            stream = self._build_symmetric_stream(
                password=password,
                payload_bytes=payload_bytes,
            )
            # ใช้ Password เป็นตัวกำหนดลำดับ Pixel (Seed)
            seed_for_order = password
            
         # --- CASE 2: Public (Asymmetric RSA) ---
        elif mode_str == "public":
            # Asymmetric (public-key based)
            if not isinstance(public_key_path, str) or not public_key_path.strip():
                raise ValueError(
                    "Public-key mode requires a  public_key file."
                )

            stream, fingerprint = self._build_asymmetric_stream(
                public_key_path=public_key_path,
                payload_bytes=payload_bytes,
            )
            # ใช้ fingerprint เป็น seed เพื่อให้ pixel order ผูกกับ public key จริง ๆ
            seed_for_order = f"asym:{fingerprint}"       
        else: # mode_str == "none"
            # สร้าง Stream แบบไม่เข้ารหัส (Plain)
            # Layout: [MODE_NONE] + [HEADER] + [PAYLOAD]
            # ต้องนิยาม MODE_NONE = 0x00 หรือค่าอื่นๆ
            header_bytes = build_plain_header(len(payload_bytes))
            stream = b"".join([bytes([0x00]), header_bytes, payload_bytes])
            seed_for_order = "default_seed" # หรือค่าคงที่อื่นๆ
            
        # 4) Build pixel order ด้วย seed_for_order
        order = build_pixel_order(entropy_map, seed_for_order)
        
         # 5) Convert stream to bits
        bits = bitutil.bytes_to_bits(stream)
        
        # 6) Prepare block map & arrays
        h, w, _ = cover.shape
        num_pixels = h * w
        flat_capacity = capacity_map.reshape(-1)
        
        # block mapping
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
        
        # pixel positions per block in "order"
        # 1. ดึง Block ID ของพิกเซลทั้งหมดตามลำดับ 'order' ในครั้งเดียว
        pixel_block_ids = block_map[order.astype(int)]

        # 2. ใช้การจัดเรียง (Sorting) เพื่อจัดกลุ่มข้อมูลที่เหมือนกันไว้ด้วยกัน
        sort_idx = np.argsort(pixel_block_ids)
        sorted_blocks = pixel_block_ids[sort_idx]

        # 3. หาจุดรอยต่อที่ Block ID เปลี่ยนเพื่อแบ่งกลุ่ม (Splitting)
        diff_idx = np.where(np.diff(sorted_blocks) != 0)[0] + 1
        split_positions = np.split(sort_idx, diff_idx)
        unique_block_ids = sorted_blocks[np.insert(diff_idx, 0, 0)]

        # 4. สร้าง Dictionary ผลลัพธ์
        block_pixel_positions = dict(zip(unique_block_ids, split_positions))
        
        
            
        # 7) Embedding
        thresholds = BlockSafetyThresholds()
        gray_for_coords = gray
        
        def adjust_cap(gray_img, y, x, req_bits):
            return adjust_capacity_for_pixel(gray_img, y, x, req_bits)

        def block_checker(orig_block, stego_block):
            return is_block_safe(orig_block, stego_block, thresholds)

        stego = cover.copy()
        

        stego = embed_bits_low_level(
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
         
        # 8) Quality metrics
        psnr_val = compute_psnr(cover, stego)
        ssim_val = compute_ssim(cover, stego)
        hist_drift_val = histogram_drift(cover, stego)
        
        metrics = EmbedMetrics(psnr=psnr_val, ssim=ssim_val, hist_drift=hist_drift_val)
        return stego, metrics
    
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
            raise Exception("Symmetric mode requires a non-empty password.")

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
            raise Exception(f"Failed to load public key: {exc}") from exc

        # 2) Generate AES-256 symmetric key (random 32 bytes)
        sym_key = generate_salt(32)  # ใช้ generate_salt เป็น random 32 bytes

        # 3) Encrypt symmetric key with RSA-OAEP
        try:
            ek = rsa_encrypt_key(public_key, sym_key)
        except Exception as exc:
            raise Exception(f"RSA encryption failed: {exc}") from exc

        ek_len = len(ek)
        if ek_len > 65535:
            raise Exception(
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
    
    # Part of Image IO
    def load_png(self, path: str) -> np.ndarray:
        """
        Load PNG (24-bit) and return as HxWx3 uint8 array.
        Reject non-PNG formats.
        """
        if not os.path.isfile(path):
            raise Exception(f"File not found: {path}")
        try:
            img = Image.open(path)
        except Exception as exc:
            raise Exception(f"Failed to open image: {exc}") from exc

        self._validate_png_image(img, path)

        if img.mode == "RGBA":
            # drop alpha (we only operate on RGB)
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        arr = np.asarray(img, dtype=np.uint8)
        if arr.ndim != 3 or arr.shape[2] != 3:
            raise Exception("Expected 24-bit RGB PNG.")
        return arr
    
    def _validate_png_image(self, img: Image.Image, path: str) -> None:
        if img.format != "PNG":
            raise Exception(f"File is not PNG: {path}")
        allowed_modes = ("RGB", "RGBA", "P", "L")
        if img.mode not in allowed_modes:
            raise Exception(f"Invalid PNG mode: {img.mode}. Supported: {allowed_modes}")