import os
import math
import struct
# import random <-- ลบออก เพราะไม่ได้ใช้สร้างขยะแล้ว
from PyQt6.QtWidgets import QFileDialog, QMessageBox

class StegoLogic:
    
    PNG_EOF_SIG = b'\x00\x00\x00\x00IEND\xaeB`\x82'
    FRAG_SIG = b'FRAG' 
    
    @staticmethod
    def select_file(app, line_edit, type_):
        filter_ = "PNG Images (*.png)" if type_ == "Image" else "All Files (*)"
        files, _ = QFileDialog.getOpenFileNames(app, "Select Files", "", filter_)
        
        if files:
            result_string = "; ".join(files)
            line_edit.setText(result_string)
            
    @staticmethod
    def fragment_payload(data: bytes) -> bytes:
        """
        แปลงข้อมูลดิบ -> ข้อมูลที่ถูกหั่นเป็นท่อนๆ (Linked List)
        Structure: [SIG(4)][NextOffset(4)][Len(4)] + [Data]
        """
        BLOCK_SIZE = 4096 
        stream = b''
        total_len = len(data)
        chunks = math.ceil(total_len / BLOCK_SIZE)
        
        for i in range(chunks):
            start = i * BLOCK_SIZE
            end = start + BLOCK_SIZE
            chunk_data = data[start:end]
            chunk_len = len(chunk_data)
            
            # คำนวณ Offset ไปยังท่อนถัดไป
            if i == chunks - 1:
                next_offset = 0 # ท่อนสุดท้าย Offset เป็น 0
            else:
                # Offset = Header(12) + Data
                next_offset = 12 + chunk_len
                
            # สร้าง Header 12 bytes
            header = struct.pack('>4sII', StegoLogic.FRAG_SIG, next_offset, chunk_len)
            
            stream += header + chunk_data
            
        return stream

    @staticmethod
    def defragment_payload(stream: bytes) -> bytes:
        """
        อ่านข้อมูลที่ถูกหั่นแบบ Linked List
        """
        clean_data = b''
        cursor = 0
        
        while cursor < len(stream):
            # 1. เช็กว่าเหลือพออ่าน Header ไหม
            if cursor + 12 > len(stream): break
            
            # 2. อ่าน Header
            sig, next_offset, length = struct.unpack('>4sII', stream[cursor:cursor+12])
            
            # 3. ตรวจสอบลายเซ็น
            if sig != StegoLogic.FRAG_SIG: break 
            
            # 4. อ่านข้อมูลจริง
            data_start = cursor + 12
            data_end = data_start + length
            clean_data += stream[data_start:data_end]
            
            # 5. ถ้า Offset 0 คือจบไฟล์
            if next_offset == 0: break
            
            # 6. กระโดดไปยังท่อนถัดไป (ตาม Offset ที่ระบุใน Header)
            cursor += next_offset
            
        return clean_data

    # =========================================================
    # RUN PROCESS
    # =========================================================

    @staticmethod
    def run_hide(app):
        """
        app: คือตัวแปร self จาก main.py เพื่อให้เราเข้าถึง txt_hide_img, txt_hide_secret ได้
        """
        raw_img_text = app.txt_hide_img.text()
        secret_path = app.txt_hide_secret.text()

        img_list = [x.strip() for x in raw_img_text.split(';') if x.strip()]

        if not img_list or not secret_path:
            QMessageBox.warning(app, "แจ้งเตือน", "กรุณาเลือกไฟล์ภาพ (อย่างน้อย 1 รูป) และไฟล์ลับให้ครบถ้วน")
            return

        if not os.path.exists(secret_path):
            QMessageBox.critical(app, "Error", f"หาไฟล์ลับไม่เจอ: {secret_path}")
            return

        # --- CASE A: Single File (Modified for Fragmentation) ---
        if len(img_list) == 1:
            img_path = img_list[0]
            save_path, _ = QFileDialog.getSaveFileName(app, "บันทึกรูปภาพ", "", "PNG Image (*.png)")
            
            if save_path:
                try:
                    # 1. อ่านไฟล์ลับเข้า RAM
                    with open(secret_path, 'rb') as f:
                        secret_data = f.read()
                    
                    # 2. ทำ Fragmentation (หั่นแบบไม่มีขยะ)
                    fragmented_data = StegoLogic.fragment_payload(secret_data)
                    
                    # 3. บันทึก
                    success, msg = StegoLogic.hide_bytes_core(img_path, fragmented_data, save_path)
                    
                    if success:
                        QMessageBox.information(app, "สำเร็จ", "ซ่อนและกระจายข้อมูล (Fragmented) เรียบร้อยแล้ว!")
                    else:
                        QMessageBox.critical(app, "ผิดพลาด", msg)
                except Exception as e:
                    QMessageBox.critical(app, "Error", str(e))

        # --- CASE B: Multiple Files (Sharding) ---
        else:
            folder_path = QFileDialog.getExistingDirectory(app, "เลือกโฟลเดอร์สำหรับบันทึกไฟล์")
            session_id = struct.unpack('>I', os.urandom(4))[0]
            
            if not folder_path:
                return

            try:
                with open(secret_path, 'rb') as f:
                    secret_data = f.read()
                
                total_size = len(secret_data)
                n_images = len(img_list)
                chunk_size = math.ceil(total_size / n_images)
                
                success_count = 0
                errors = []

                for i, img_path in enumerate(img_list):
                    try:
                        start = i * chunk_size
                        end = start + chunk_size
                        part_data = secret_data[start:end]

                        header = struct.pack('>III', session_id,i, n_images) 
                        final_payload = header + part_data

                        base_name = os.path.basename(img_path)
                        name_no_ext, _ = os.path.splitext(base_name)
                        new_filename = f"{name_no_ext}.png"
                        full_save_path = os.path.join(folder_path, new_filename)

                        # เรียก Logic
                        success, msg = StegoLogic.hide_bytes_core(img_path, final_payload, full_save_path)
                        
                        if success:
                            success_count += 1
                        else:
                            errors.append(f"{base_name}: {msg}")

                    except Exception as e_inner:
                        errors.append(f"{img_path}: {str(e_inner)}")

                result_msg = f"กระจายข้อมูลลับลงใน {success_count} จาก {n_images} รูปเรียบร้อยแล้ว"
                if errors:
                    result_msg += "\n\nพบปัญหาบางไฟล์:\n" + "\n".join(errors)
                    QMessageBox.warning(app, "เสร็จสิ้น (มีข้อผิดพลาด)", result_msg)
                else:
                    QMessageBox.information(app, "เสร็จสิ้นสมบูรณ์", result_msg)

            except Exception as e_outer:
                QMessageBox.critical(app, "Critical Error", f"เกิดข้อผิดพลาดร้ายแรงในการอ่านไฟล์ลับ: {str(e_outer)}")

    @staticmethod
    def run_extract(app):
        raw_text = app.txt_ext_img.text()
        if not raw_text:
            QMessageBox.warning(app, "แจ้งเตือน", "กรุณาเลือกรูปภาพก่อน")
            return

        img_list = [x.strip() for x in raw_text.split(';') if x.strip()]
        
        save_path, _ = QFileDialog.getSaveFileName(app, "ตั้งชื่อไฟล์ผลลัพธ์", "", "All Files (*)")
        if not save_path: return

        try:
            # --- CASE A: ไฟล์เดียว (Modified for Defragmentation) ---
            if len(img_list) == 1:
                img_path = img_list[0]
                payload, msg = StegoLogic.get_raw_payload_core(img_path)
                
                if payload:
                    # พยายามรวมชิ้นส่วน (Defragment)
                    real_data = StegoLogic.defragment_payload(payload)
                    
                    if not real_data:
                        # Fallback: ถ้า Defrag ไม่ได้ (อาจเป็นไฟล์แบบเก่า)
                        QMessageBox.warning(app, "เตือน", "ไม่พบโครงสร้างข้อมูลแบบ Fragmented หรือข้อมูลเสียหาย")
                        return

                    with open(save_path, 'wb') as f: f.write(real_data)
                    QMessageBox.information(app, "สำเร็จ", f"รวมข้อมูลและบันทึกที่: {save_path}")
                else:
                    QMessageBox.critical(app, "ผิดพลาด", msg)

            # --- CASE B: หลายไฟล์ (Reassembling) ---
            else:
                found_parts = []
                errors = []
                
                expected_session_id = None

                for img_path in img_list:
                    base_name = os.path.basename(img_path)
                    payload, msg = StegoLogic.get_raw_payload_core(img_path)
                    
                    if payload:
                        try:
                            # *** เช็ก Header 8 bytes ***
                            if len(payload) >= 12:

                                sess_id, index, total_count = struct.unpack('>III', payload[:12])
                                content = payload[12:]
                                
                                if expected_session_id is None:
                                    expected_session_id = sess_id
                                    
                                if sess_id != expected_session_id:
                                    errors.append(f"{base_name}: Session ID ไม่ตรง (คนละชุดข้อมูล)")
                                    continue
                                
                                found_parts.append({
                                    'index': index,
                                    'total': total_count,
                                    'data': content,
                                    'filename': base_name
                                })
                            else:
                                errors.append(f"{base_name}: ข้อมูลสั้นเกินไป (ไม่พบ Header)")
                        except Exception as e:
                            errors.append(f"{base_name}: Header Error ({e})")
                    else:
                        errors.append(f"{base_name}: {msg}")

                if not found_parts:
                    QMessageBox.critical(app, "ล้มเหลว", "ไม่พบข้อมูลในไฟล์ที่เลือกเลย")
                    return
                
                # เรียงลำดับตาม Index
                found_parts.sort(key=lambda x: x['index'])

                # เช็กจำนวน
                expected_total = found_parts[0]['total'] 
                current_count = len(found_parts)

                if current_count != expected_total:
                    msg = f"ชิ้นส่วนไม่ครบ!\nเจอ {current_count} ส่วน จากที่ควรมี {expected_total} ส่วน\n\nไฟล์ที่ได้อาจจะไม่สมบูรณ์ ต้องการทำต่อหรือไม่?"
                    reply = QMessageBox.question(app, "Warning", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    if reply == QMessageBox.StandardButton.No: return

                # รวมร่าง
                full_data = b''.join([part['data'] for part in found_parts])

                with open(save_path, 'wb') as f:
                    f.write(full_data)
                
                QMessageBox.information(app, "สำเร็จ", "รวมไฟล์และบันทึกสำเร็จ!")

        except Exception as e:
            QMessageBox.critical(app, "Error", f"เกิดข้อผิดพลาด: {str(e)}")

    # =========================================================
    # ส่วนที่ 2: CORE LOGIC (การคำนวณไบนารีล้วนๆ)
    # =========================================================

    @staticmethod
    def hide_file_core(carrier_path, secret_path, output_path):
        try:
            with open(carrier_path, 'rb') as f_img:
                img_data = f_img.read()
            with open(secret_path, 'rb') as f_secret:
                secret_data = f_secret.read()
            new_data = img_data + secret_data
            with open(output_path, 'wb') as f_out:
                f_out.write(new_data)
            return True, "Success"
        except Exception as e:
            return False, str(e)
       
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
            
            # 1. หาจุดสิ้นสุดของ PNG (IEND)
            eof_index = all_data.find(StegoLogic.PNG_EOF_SIG)
            if eof_index == -1:
                return None, "ไม่ใช่ไฟล์ PNG หรือไฟล์เสียหาย"
            
            # 2. คำนวณจุดเริ่มต้นข้อมูลที่ซ่อน
            split_point = eof_index + len(StegoLogic.PNG_EOF_SIG)
            
            # 3. ถ้าไม่มีข้อมูลต่อท้ายเลย
            if split_point >= len(all_data):
                return None, "ไม่พบข้อมูลซ่อนอยู่"
            
            secret_data = all_data[split_point:]
            return secret_data, "Success"
        except Exception as e:
            return None, str(e)