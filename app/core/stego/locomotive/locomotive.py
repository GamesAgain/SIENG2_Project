import os
import math
import struct
import random
import time
from typing import List, Optional, Callable

# --- Crypto Imports (ใช้ชุดเดียวกับ LSB++ เพื่อความปลอดภัย) ---
from app.core.crypto.sym_crypto import (
    derive_key_argon2id, 
    generate_salt, 
    aes_gcm_encrypt
)
from app.core.crypto.asym_crypto import (
    load_public_key_pem, 
    rsa_encrypt_key
)

class Locomotive:
    
    PNG_EOF_SIG = b'\x00\x00\x00\x00IEND\xaeB`\x82'
    FRAG_SIG = b'FRAG' 
    
    # =========================================================
    # 1. MAIN INTERFACE (เรียกโดย EmbedWorker)
    # =========================================================
    def embed(
        self,
        cover_paths: List[str],      # รับเป็น List ของ Path รูปภาพ
        payload_path: str,           # รับเป็น Path ไฟล์ลับ
        encrypt_mode: str,           # 'password', 'public', 'none'
        password: Optional[str] = None,
        public_key_path: Optional[str] = None,
        status_callback: Optional[Callable[[str, int], None]] = None
    ) -> str:
        """
        Main Entry Point สำหรับ EmbedWorker
        Returns: Path ของโฟลเดอร์หรือไฟล์ผลลัพธ์
        """
        def update(text, percent):
            if status_callback: status_callback(text, percent)

        # 1. ตรวจสอบไฟล์
        update("Reading payload...", 5)
        if not os.path.exists(payload_path):
            raise FileNotFoundError(f"Payload file not found: {payload_path}")

        with open(payload_path, 'rb') as f:
            raw_data = f.read()

        # 2. เข้ารหัสข้อมูล (Encryption Layer)
        update("Encrypting data...", 15)
        final_payload = self._encrypt_data(raw_data, encrypt_mode, password, public_key_path)

        # 3. เตรียม Output
        # สร้างโฟลเดอร์ locomotive_output ในระดับเดียวกับรูปแรก
        base_dir = os.path.dirname(cover_paths[0])
        output_dir = os.path.join(base_dir, "locomotive_output")
        os.makedirs(output_dir, exist_ok=True)
        
        n_images = len(cover_paths)

        # --- CASE A: Single File (Fragmentation) ---
        if n_images == 1:
            update("Processing Single Image...", 30)
            cover_path = cover_paths[0]
            
            # Logic เดิม: Fragment -> Shuffle
            update("Fragmenting & Shuffling...", 40)
            fragmented_data = self.fragment_payload(final_payload)
            
            # สร้างชื่อไฟล์ผลลัพธ์
            filename = os.path.basename(cover_path)
            name, ext = os.path.splitext(filename)
            save_path = os.path.join(output_dir, f"{name}_loco{ext}")
            
            # ฝังข้อมูล
            update("Embedding data...", 70)
            success, msg = self.hide_bytes_core(cover_path, fragmented_data, save_path)
            
            if not success:
                raise Exception(f"Embedding failed: {msg}")
            
            update("Done.", 100)
            return save_path

        # --- CASE B: Multiple Files (Sharding) ---
        else:
            update(f"Processing {n_images} Images (Sharding)...", 30)
            
            total_size = len(final_payload)
            chunk_size = math.ceil(total_size / n_images)
            
            session_id = struct.unpack('>I', os.urandom(4))[0]
            
            for i, img_path in enumerate(cover_paths):
                # Update progress ตามจำนวนรูป
                progress = 30 + int((i / n_images) * 60)
                update(f"Embedding image {i+1}/{n_images}...", progress)
                
                # ตัดแบ่งข้อมูล
                start = i * chunk_size
                end = start + chunk_size
                part_data = final_payload[start:end]

                # Header Sharding: [SessionID] [Index] [Total]
                header = struct.pack('>III', session_id, i, n_images) 
                chunk_final = header + part_data

                # สร้างชื่อไฟล์
                base_name = os.path.basename(img_path)
                name, ext = os.path.splitext(base_name)
                # ตั้งชื่อเป็น part_1, part_2 เพื่อให้รู้ลำดับ
                save_path = os.path.join(output_dir, f"{name}_part_{i+1}{ext}")

                # ฝังข้อมูล
                success, msg = self.hide_bytes_core(img_path, chunk_final, save_path)
                
                if not success:
                    raise Exception(f"Failed at {base_name}: {msg}")

            update("Done.", 100)
            return output_dir

    # =========================================================
    # 2. HELPER METHODS (Pure Logic)
    # =========================================================
    
    def _encrypt_data(self, data: bytes, mode: str, pwd: str, pub_key: str) -> bytes:
        """เข้ารหัสข้อมูลก่อนนำไป Fragment/Shard"""
        mode = (mode or "none").lower()
        
        # ใส่ Header เล็กๆ เพื่อระบุโหมดการเข้ารหัส [Mode Byte] + [Data]
        # 0x00=None, 0x01=Password, 0x02=Public Key
        
        if mode == "password":
            if not pwd: raise ValueError("Password required")
            salt = generate_salt()
            key = derive_key_argon2id(pwd, salt)
            nonce, ciphertext = aes_gcm_encrypt(key, data)
            # Format: [0x01] [SALT(16)] [NONCE(12)] [CIPHERTEXT]
            return b'\x01' + salt + nonce + ciphertext
            
        elif mode == "public":
            if not pub_key: raise ValueError("Public Key required")
            pk = load_public_key_pem(pub_key)
            sym_key = generate_salt(32) # Ephemeral Key
            ek = rsa_encrypt_key(pk, sym_key)
            nonce, ct = aes_gcm_encrypt(sym_key, data)
            # Format: [0x02] [EK_LEN(2)] [EK] [NONCE(12)] [CIPHERTEXT]
            return b'\x02' + len(ek).to_bytes(2, 'big') + ek + nonce + ct
            
        else:
            # Format: [0x00] [DATA]
            return b'\x00' + data

    @staticmethod
    def fragment_payload(data: bytes) -> bytes:
        """
        หั่นข้อมูล -> แปะเบอร์ลำดับ -> สับตำแหน่ง (Shuffle)
        Structure: [SIG(4)][Index(4)][Len(4)] + [Data]
        """
        BLOCK_SIZE = 4096 
        total_len = len(data)
        chunks_count = math.ceil(total_len / BLOCK_SIZE)
        
        chunk_list = []
        
        for i in range(chunks_count):
            start = i * BLOCK_SIZE
            end = start + BLOCK_SIZE
            chunk_data = data[start:end]
            
            chunk_list.append({
                'index': i,
                'data': chunk_data
            })
            
        random.shuffle(chunk_list)
        
        final_stream = b''
        for item in chunk_list:
            idx = item['index']
            chunk_data = item['data']
            chunk_len = len(chunk_data)
            
            # ใช้ Locomotive.FRAG_SIG หรือ self.FRAG_SIG
            header = struct.pack('>4sII', Locomotive.FRAG_SIG, idx, chunk_len)
            final_stream += header + chunk_data
            
        return final_stream

    @staticmethod
    def defragment_payload(stream: bytes) -> bytes:
        found_chunks = []
        cursor = 0
        stream_len = len(stream)
        
        while cursor < stream_len:
            if cursor + 12 > stream_len: break
            
            sig, idx, length = struct.unpack('>4sII', stream[cursor:cursor+12])
            
            if sig != Locomotive.FRAG_SIG: break
            
            data_start = cursor + 12
            data_end = data_start + length
            
            if data_end > stream_len: break
                
            chunk_data = stream[data_start:data_end]
            found_chunks.append({'index': idx, 'data': chunk_data})
            cursor = data_end
            
        if not found_chunks: return None

        found_chunks.sort(key=lambda x: x['index'])
        return b''.join([item['data'] for item in found_chunks])

    @staticmethod    
    def hide_bytes_core(carrier_path, secret_data_bytes, output_path):
        try:
            with open(carrier_path, 'rb') as f_img:
                img_data = f_img.read()
            new_data = img_data + secret_data_bytes
            with open(output_path, 'wb') as f_out:
                f_out.write(new_data)
            return True, "Success"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def get_raw_payload_core(stego_image_path):
        try:
            with open(stego_image_path, 'rb') as f:
                all_data = f.read()
            
            eof_index = all_data.find(Locomotive.PNG_EOF_SIG)
            if eof_index == -1:
                return None, "Not a valid PNG or damaged"
            
            split_point = eof_index + len(Locomotive.PNG_EOF_SIG)
            
            if split_point >= len(all_data):
                return None, "No hidden data found"
            
            secret_data = all_data[split_point:]
            return secret_data, "Success"
        except Exception as e:
            return None, str(e)