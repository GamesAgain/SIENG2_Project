import os
import math

# ============================================================================
# CONSTANTS (ค่าคงที่สำหรับตรวจสอบโครงสร้างไฟล์)
# ============================================================================
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
PNG_IEND_CHUNK = b'IEND\xae\x42\x60\x82'  # IEND Chunk + CRC

# ============================================================================
# GENERAL FILE UTILITIES (จัดการข้อมูลไฟล์ทั่วไป)
# ============================================================================

def format_file_size(size_bytes: int) -> str:
    """
    แปลงขนาดไฟล์เป็นหน่วยที่มนุษย์อ่านง่าย (B, KB, MB, GB)
    """
    if size_bytes == 0:
        return "0 B"
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {units[i]}"

def truncate_filename(filename: str, max_length: int = 20) -> str:
    """
    ย่อชื่อไฟล์หากยาวเกินไป เช่น 'very_long_file_name.png' -> 'very_long...png'
    """
    if len(filename) <= max_length:
        return filename
    name, ext = os.path.splitext(filename)
    trim_len = max_length - len(ext) - 2
    if trim_len > 0:
        return f"{name[:trim_len]}..{ext}"
    return filename

def get_file_info(file_path: str) -> dict:
    """
    ดึงข้อมูลพื้นฐานของไฟล์เพื่อแสดงผลใน GUI หรือ Report
    """
    if not os.path.exists(file_path):
        return None
    
    size = os.path.getsize(file_path)
    return {
        "name": os.path.basename(file_path),
        "path": file_path,
        "size_bytes": size,
        "size_str": format_file_size(size),
        "ext": os.path.splitext(file_path)[1].lower()
    }

# ============================================================================
# BINARY I/O (การอ่านเขียนไฟล์แบบ Binary)
# ============================================================================

def read_file_binary(file_path: str) -> bytes:
    """
    อ่านไฟล์ทั้งหมดเป็น Binary Bytes (สำหรับเตรียมเข้ารหัสหรือฝัง)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    with open(file_path, "rb") as f:
        return f.read()

def save_file_binary(file_path: str, data: bytes) -> bool:
    """
    บันทึกข้อมูล Binary ลงไฟล์ (ใช้สร้าง Stego File หรือ Export ข้อมูลที่ถอดได้)
    """
    try:
        with open(file_path, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"Error saving file {file_path}: {e}")
        return False

# ============================================================================
# LOCOMOTIVE TECHNIQUE SUPPORT (การต่อท้ายไฟล์และการแบ่งส่วน)
# ============================================================================

def append_data_to_png(cover_path: str, output_path: str, data_to_hide: bytes) -> bool:
    """
    [Locomotive Technique] นำข้อมูลไปต่อท้ายไฟล์ PNG หลัง IEND Chunk
    """
    try:
        # 1. อ่านไฟล์ต้นฉบับ
        cover_data = read_file_binary(cover_path)
        
        # 2. ตรวจสอบว่าเป็น PNG หรือไม่
        if not cover_data.startswith(PNG_SIGNATURE):
            raise ValueError("Input file is not a valid PNG.")

        # 3. หาตำแหน่งจบของ PNG จริงๆ (หลัง IEND Chunk)
        iend_index = cover_data.find(PNG_IEND_CHUNK)
        if iend_index == -1:
            raise ValueError("IEND Chunk not found. File might be corrupted.")
        
        # จุดสิ้นสุดของไฟล์มาตรฐานคือ หลัง IEND (4 bytes 'IEND' + 4 bytes CRC)
        end_of_png = iend_index + len(PNG_IEND_CHUNK)
        
        # 4. สร้างข้อมูลใหม่: เนื้อหา PNG เดิม + ข้อมูลลับที่ต่อท้าย
        new_data = cover_data[:end_of_png] + data_to_hide
        
        # 5. บันทึกไฟล์ใหม่
        return save_file_binary(output_path, new_data)
        
    except Exception as e:
        print(f"Locomotive Append Error: {e}")
        return False

def extract_tail_data(stego_path: str) -> bytes:
    """
    [Steganalysis & Extraction] ดึงข้อมูลส่วนเกินที่อยู่หลัง IEND Chunk ออกมา 
    """
    try:
        file_data = read_file_binary(stego_path)
        
        # หา IEND Chunk
        iend_index = file_data.find(PNG_IEND_CHUNK)
        if iend_index == -1:
            return b"" # ไม่พบ IEND
            
        end_of_png = iend_index + len(PNG_IEND_CHUNK)
        
        # ถ้ามีข้อมูลต่อท้าย ให้คืนค่านั้นกลับไป (Tail Data)
        if len(file_data) > end_of_png:
            return file_data[end_of_png:]
        
        return b"" # ไม่มีข้อมูลต่อท้าย
        
    except Exception as e:
        print(f"Extract Tail Error: {e}")
        return b""

# ============================================================================
# FRAGMENTATION (การแบ่งไฟล์สำหรับ Configurable Models) 
# ============================================================================

def split_data(data: bytes, num_chunks: int) -> list[bytes]:
    """
    แบ่งข้อมูล Binary ออกเป็นส่วนๆ (Fragmentation) เพื่อกระจายฝังในหลายไฟล์
    ใช้สำหรับเทคนิค Locomotive แบบกระจาย หรือ Configurable Models
    """
    if num_chunks <= 1:
        return [data]
        
    chunk_size = math.ceil(len(data) / num_chunks)
    return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

def merge_data(chunks: list[bytes]) -> bytes:
    """
    รวมข้อมูลที่ถูกแบ่งส่วนกลับเป็นก้อนเดียว
    """
    return b"".join(chunks)

# ============================================================================
# INTEGRITY CHECK (ตรวจสอบความถูกต้องไฟล์)
# ============================================================================

def verify_png_signature(file_path: str) -> bool:
    """
    ตรวจสอบ Magic Bytes ว่าเป็น PNG ถูกต้องหรือไม่
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(len(PNG_SIGNATURE))
            return header == PNG_SIGNATURE
    except Exception:
        return False