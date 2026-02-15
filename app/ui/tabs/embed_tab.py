# PYQT6 FRAMEWORK (GUI)
import shutil
import os
from PyQt6.QtCore import (
    Qt, QTimer, QSize, pyqtSignal, QMimeData, QThread
)

from PyQt6.QtGui import (
    QPixmap, QFont, QDragEnterEvent, QDropEvent, QResizeEvent, QIcon, QPainter, QColor, QPen
)
import base64
from PyQt6.QtCore import QByteArray

from PyQt6.QtWidgets import (
    # Windows & Containers
    QApplication, QMainWindow, QWidget, QDialog, 
    QStackedWidget, QTabWidget, QGroupBox, QScrollArea, QSplitter,
    
    # Layouts
    QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QSizePolicy, QStackedLayout,
    
    # Input Widgets
    QPushButton, QLineEdit, QTextEdit, QComboBox,
    
    # Display Widgets
    QLabel, QProgressBar, QListWidget, QListWidgetItem, QMessageBox, QAbstractItemView,
    QTableWidget, QTableWidgetItem, QHeaderView,
    
    # Utilities
    QFileDialog, QStyle
)

from app.core.stego.lsb_plus.engine.noise_predictor import adjust_capacity_for_pixel
from app.core.stego.lsb_plus.engine.pixel_order import build_pixel_order
from app.core.stego.metadata_engine.metadata import MetadataEditorWidget
from app.ui.components.loco_file import LocoFileTile

try:
    from PIL import Image
except ImportError:
    Image = None
    
    
from app.core.stego.lsb_plus.engine.embedding import calculate_exact_capacity
from app.core.stego.lsb_plus.lsbpp import LSBPP
from app.core.stego.locomotive.locomotive import Locomotive
from app.utils.file_io import format_file_size
from app.utils.gui_helpers import disconnect_signal_safely

import numpy as np
import uuid
import json
from app.core.stego.lsb_plus.engine.analyzer.capacity import compute_capacity
from app.core.stego.lsb_plus.engine.analyzer.texture_map import compute_texture_features


# ============================================================================
# CONSTANTS & STYLES
# ============================================================================

PAGE_LSB = 0
PAGE_LOCOMOTIVE = 1
PAGE_METADATA = 2


#For switch self.payload_stack section
PAGE_PAYLOAD_INPUT = 0
PAGE_CARRIER_PREVIEW = 1

TAB_INDEX_TEXT = 0
TAB_INDEX_FILE = 1

LOCO_LIST_STYLE = """
QListWidget {
    background-color: #1e1e1e;
    border: 1px solid #444;
    border-radius: 6px;
}
QListWidget::item:selected {
    background-color: #2d5a75;
    border: 2px solid #3daee9;
    border-radius: 6px;
}
QListWidget::item:hover {
    background-color: #2a2a2a;
    border-radius: 6px;
}
"""

# Text file extensions for LSB++ mode (100+ file types)
TEXT_FILE_EXTENSIONS = {
    # Text files
    '.txt', '.md', '.markdown', '.rst', '.csv', '.tsv', 
    '.json', '.xml', '.yaml', '.yml', '.toml', '.log',
    
    # Code files - Python, JavaScript, TypeScript
    '.py', '.pyw', '.pyx', '.js', '.jsx', '.ts', '.tsx', '.mjs',
    
    # Code files - Java, C/C++, C#
    '.java', '.c', '.cpp', '.cc', '.cxx', '.h', '.hpp', '.cs',
    
    # Code files - Other languages
    '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala',
    '.r', '.m', '.lua', '.pl', '.pm', '.sh', '.bash', '.zsh',
    
    # Web files
    '.html', '.htm', '.css', '.scss', '.sass', '.less',
    '.vue', '.svelte', '.astro',
    
    # Config files
    '.ini', '.conf', '.cfg', '.config', '.env', '.properties',
    
    # Script files
    '.sql', '.bat', '.cmd', '.ps1', '.psm1',
    
    # Data files
    '.geojson', '.kml', '.gpx', '.vcf',
    
    # Other
    '.gitignore', '.dockerignore', '.editorconfig', '.prettierrc',
    '.eslintrc', '.babelrc', '.npmrc', '.nvmrc'
}

class CapacityWorker(QThread):
    finished_signal = pyqtSignal(int, int)

    def __init__(self, image_path):
        super().__init__()
        self.image_path = image_path

    def run(self):
        try:
            if not os.path.exists(self.image_path):
                self.finished_signal.emit(0, 0)
                return

            img = Image.open(self.image_path).convert("RGB")
            rgb = np.asarray(img, dtype=np.uint8)
            h, w, _ = rgb.shape

            # 1. วิเคราะห์
            gray, _, entropy_map, surface_map = compute_texture_features(rgb)
            capacity_map = compute_capacity(surface_map)
            
            # 2. Pixel Order
            default_seed = "default_seed" 
            order = build_pixel_order(entropy_map, default_seed)

            # 3. คำนวณความจุ (V8 Synced)
            total_bits = calculate_exact_capacity(
                order, 
                capacity_map.ravel(), 
                gray, 
                adjust_capacity_for_pixel, 
                w
            )

            raw_bytes = int(total_bits // 8)
            
            # Overhead 52 bytes (Mode 1 + Header 7 + Salt 16 + Nonce 12 + Tag 16)
            sym_overhead = 52       
            asym_overhead = 566

            # Max Limit: Raw - 52
            # ถ้า Raw = 80 -> Max = 28 (ถูกต้องตามที่คุณต้องการ)
            limit_max = max(0, raw_bytes - sym_overhead)
            limit_safe = max(0, raw_bytes - asym_overhead)

            self.finished_signal.emit(limit_safe, limit_max)

        except Exception as e:
            print(f"Capacity calculation failed: {e}")
            self.finished_signal.emit(0, 0)

class EmbedWorker(QThread):
    # Signal ส่งผลลัพธ์กลับ (Result, Metrics)
    # LSB: Result=RGB Array, Metrics=Object
    # Locomotive: Result=Output Path, Metrics=None (หรือตาม Engine ส่งมา)
    finished_signal = pyqtSignal(object, object)
    error_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(str, int) 

    def __init__(self, engine, cover_source, payload_source, mode_str, pwd, pub_key, on_tech):
        super().__init__()
        self.engine = engine
        self.cover_source = cover_source     # LSB: str (Path) | Locomotive: list (Paths)
        self.payload_source = payload_source # LSB: str (Text Data) | Locomotive: str (File Path)
        self.mode_str = mode_str
        self.pwd = pwd
        self.pub_key = pub_key
        self.on_tech = on_tech               # 'LSB' or 'Locomotive'

    def run(self):
        """Background Thread"""
        try:
            # Callback สำหรับส่ง Progress กลับไปที่ UI
            def worker_callback(text, percent):
                self.progress_signal.emit(text, percent)
                
            if self.on_tech == 'LSB':
                # ... (ส่วน LSB เหมือนเดิม ถูกแล้ว) ...
                stego_rgb, metrics = self.engine.embed(
                    cover_path=self.cover_source,
                    payload_text=self.payload_source, 
                    encrypt_mode=self.mode_str,
                    password=self.pwd,
                    public_key_path=self.pub_key,
                    status_callback=worker_callback
                )
                self.finished_signal.emit(stego_rgb, metrics)
                
            elif self.on_tech == 'Locomotive':
                # === [FIXED] Locomotive Logic ===
                result = self.engine.embed(
                    cover_paths=self.cover_source,    # แก้ชื่อเป็น cover_paths (ตาม Engine)
                    payload_path=self.payload_source, # แก้ชื่อเป็น payload_path (ตาม Engine)
                    encrypt_mode=self.mode_str,       # ส่งโหมดเข้ารหัส
                    password=self.pwd,                # ส่งรหัสผ่าน
                    public_key_path=self.pub_key,     # ส่ง Public Key
                    status_callback=worker_callback   # ส่ง Callback เพื่อให้หลอดโหลดขยับ!
                )
                
                # Locomotive ส่งค่ากลับมาเป็น Path (String) ไม่ใช่ Image Array
                self.finished_signal.emit(result, None)
                
        except Exception as e:
            self.error_signal.emit(str(e))
# ============================================================================
# CUSTOM WIDGETS
# ============================================================================

from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import pyqtSignal, Qt

from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import pyqtSignal

from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import pyqtSignal

class DraggablePreviewLabel(QLabel):
    """
    QLabel with drag-and-drop support.
    allowed_extensions: list of strings (e.g., ['.png', '.jpg']) or None for all files.
    """
    file_dropped = pyqtSignal(str)  # Emit file path when image dropped
    
    def __init__(self, parent=None, allowed_extensions=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._original_style = ""
        
        # จัดการเรื่องนามสกุลไฟล์
        if allowed_extensions:
            # แปลงเป็น tuple และทำเป็นตัวพิมพ์เล็กทั้งหมด
            # เติม . ถ้า user ลืมใส่ (เช่น ส่งมาแค่ 'png' -> '.png')
            processed_exts = []
            for ext in allowed_extensions:
                ext = ext.lower()
                if not ext.startswith('.'):
                    ext = '.' + ext
                processed_exts.append(ext)
            self.allowed_extensions = tuple(processed_exts)
        else:
            self.allowed_extensions = None # None แปลว่ารับทุกไฟล์ (Default)

    def is_extension_allowed(self, file_path):
        """Helper function to check extension"""
        # ถ้าเป็น None (Default) ให้ผ่านหมด หรือ ถ้ามีนามสกุลที่กำหนดให้เช็ค
        if self.allowed_extensions is None:
            return True
        return file_path.lower().endswith(self.allowed_extensions)
    
    def dragEnterEvent(self, event):
        """Handle drag enter"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1:
                file_path = urls[0].toLocalFile()
                
                # ใช้ Helper function เช็ค
                if self.is_extension_allowed(file_path):
                    event.acceptProposedAction()
                    
                    # Visual feedback logic (คงเดิมตามที่คุณต้องการ)
                    self._original_style = self.styleSheet()
                    # หมายเหตุ: การใช้ replace จะทำงานได้ต่อเมื่อมี style เดิมที่มี text นี้อยู่แล้ว
                    new_style = self._original_style.replace('border: 2px dashed #555', 'border: 2px dashed #3daee9')
                    self.setStyleSheet(new_style)
                    return
        event.ignore()
    
    def dragLeaveEvent(self, event):
        """Restore original style when drag leaves"""
        if self._original_style:
            self.setStyleSheet(self._original_style)
            # ไม่ reset self._original_style ที่นี่ เพื่อความชัวร์ในการ restore ครั้งถัดไป
            # หรือถ้า logic เดิมคุณ ok แล้วก็ปล่อยไว้
    
    def dropEvent(self, event):
        """Handle file drop"""
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            
            # ใช้ Helper function เช็คอีกรอบตอนปล่อย
            if self.is_extension_allowed(file_path):
                self.file_dropped.emit(file_path)
                event.acceptProposedAction()
        
        # Restore original style
        if self._original_style:
            self.setStyleSheet(self._original_style)
            
from app.ui.components.attachment_drop_widget import AttachmentDropWidget
from app.ui.components.metadata_drop_widget import MetadataDropWidget
from app.ui.dialogs.text_editor_dialog import TextEditorDialog

class EmbedTab(QWidget):
    def __init__(self):
       super().__init__()
       
       self.locomotive_files = []
       self.original_lsb_preview_pixmaps = {}  # Store original pixmaps for scaling
       self.original_meta_preview_pixmaps = {}
       # Configurable Editor: pipeline data (list of {id, technique, encrypted, display})
       self.embed_pipeline = []
       self.extract_pipeline = []
       self.init_ui()
       
    def init_ui(self):
        self.setMinimumSize(1000, 700)
        
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)
        
        left_panel = self.create_left_panel()
        right_panel = self.create_right_panel()
        
        #ratio: left panel gets 35%, right panel gets 65%
        main_layout.addWidget(left_panel, 35)
        main_layout.addWidget(right_panel, 65)
        
        self.on_technique_changed()
                
    def on_technique_changed(self):
        current_tech = self.tech_combo.currentText()
        is_LSBPP = "LSB++" in current_tech
        is_locomotive = "Locomotive" in current_tech
        is_metadata = "Metadata" in current_tech
        
        self.reset_inputs()
        
        disconnect_signal_safely(self.carrier_browse_btn.clicked)
        
        if is_LSBPP:
            self.switch_to_lsb_mode()
            self.carrier_browse_btn.clicked.connect(self.browse_LSB_Cover_file)     
        elif is_locomotive:
            self.switch_to_locomotive_mode()
            self.carrier_browse_btn.clicked.connect(self.browse_locomotive_files)
        elif is_metadata:
            self.switch_to_metadata_mode()
            self.carrier_browse_btn.clicked.connect(self.browse_metadata_file)
            
    def on_mode_changed(self):
        is_config = self.mode_combo.currentText() == "Configurable Model"

        # Show/Hide Config Editor
        if hasattr(self, "config_editor"):
            self.config_editor.setVisible(is_config)

        # Hide/Show Standalone (LSB++) Execution Group Container
        if hasattr(self, "std_execution_container"):
            self.std_execution_container.setVisible(not is_config)
        
        # Hide/Show Locomotive Execution Group Container
        if hasattr(self, "loco_execution_container"):
            self.loco_execution_container.setVisible(not is_config)

        self.on_technique_changed()

    
    def reset_inputs(self):
        """
        Resets all inputs, preview, stats, and internal state to default.
        Called when technique changes or manual reset is needed.
        """
        
        # 1. เคลียร์ตัวแปรเก็บข้อมูล (Data Variables)
        self.current_file_path = None
        self.locomotive_files = []
        self.original_lsb_preview_pixmaps = None  # ล้าง Cache ภาพต้นฉบับ
        self.original_meta_preview_pixmaps = None
        self.limit_safe = 0
        self.limit_max = 0

        # 2. หยุด Worker คำนวณความจุที่อาจรันค้างอยู่
        if hasattr(self, 'cap_worker') and self.cap_worker.isRunning():
            self.cap_worker.terminate()
            self.cap_worker.wait()

        # 3. รีเซ็ตช่องเลือกภาพ (Carrier Input)
        if hasattr(self, 'carrier_edit'):
            self.carrier_edit.clear()

        # 4. รีเซ็ตส่วน Payload (Payload Inputs)
        if hasattr(self, 'payload_text'):
            self.payload_text.clear()
        
        if hasattr(self, 'payload_file_path'):
            self.payload_file_path.clear()
            
        if hasattr(self, 'attachment_widget'):
            try:
                self.attachment_widget.set_file(None) 
            except Exception:
                pass
        
        if hasattr(self, 'payload_tabs'):
            self.payload_tabs.setCurrentIndex(TAB_INDEX_TEXT)

        # [IMPROVED] 5. ตัดส่วนรีเซ็ต Encryption ออก
        # เพื่อให้ Password/Public Key ยังคงอยู่เมื่อสลับโหมด
        # (ไม่ต้อง clear self.passphrase, self.public_key_edit)

        # 6. รีเซ็ตภาพพรีวิว (Reset Preview Area)
        if hasattr(self, 'preview_label'):
            self.preview_label.clear()
            self.preview_label.setText("No Image Selected\n\nSelect PNG image from left panel\nor drag & drop PNG file here")
            self.preview_label.setStyleSheet("""
                QLabel {
                    border: 2px dashed #555;
                    background-color: #222;
                    color: #888;
                    font-size: 10pt;
                }
            """)
            
        if hasattr(self, 'meta_preview_label'):
            self.meta_preview_label.clear()
            self.meta_preview_label.setText("No File Selected\n\ndrag & drop file (JPG, PNG, MP3) here")
            self.meta_preview_label.setStyleSheet("""
                QLabel {
                    border: 2px dashed #555;
                    background-color: #222;
                    color: #888;
                    font-size: 10pt;
                }
            """)
            
        # 7. รีเซ็ตค่าสถิติและความจุ (Reset Stats & Capacity)
        if hasattr(self, 'update_lsb_preview_stats'):
            self.update_lsb_preview_stats(None)
            
        if hasattr(self, 'update_meta_preview_stats'):
            self.update_meta_preview_stats(None)
        
        if hasattr(self, 'lbl_capacity'):
            self.lbl_capacity.setText("Size: 0 B")
            self.lbl_capacity.setStyleSheet("color: #aaa; font-size: 8pt;")
            self.lbl_capacity.setToolTip("")

        # 8. รีเซ็ตรายการ Locomotive
        if hasattr(self, '_update_locomotive_ui_state'):
            self.update_locomotive_ui_state()
        if hasattr(self, '_update_locomotive_list'):
            self.update_locomotive_list()

        # [IMPROVED] 9. รีเซ็ตปุ่มและสถานะการทำงาน (Reset Execution State)
        # แก้ปัญหา: สั่งรีเซ็ตปุ่มของทั้ง 2 โหมดโดยตรง เพื่อป้องกันปัญหาตัวแปรทับซ้อน
        
        # 9.1 Reset Standalone Controls (LSB++)
        if hasattr(self, 'std_btn_savestg'):
            self.std_btn_savestg.hide()
            self.std_btn_savestg.setEnabled(False)
        if hasattr(self, 'std_btn_exec'):
            self.std_btn_exec.setEnabled(True)
        if hasattr(self, 'std_progress_bar'):
            self.std_progress_bar.setValue(0)
        if hasattr(self, 'std_status_label'):
            self.std_status_label.setText("Ready.")

        # 9.2 Reset Locomotive Controls
        if hasattr(self, 'loco_btn_savestg'):
            self.loco_btn_savestg.hide()
            self.loco_btn_savestg.setEnabled(False)
        if hasattr(self, 'loco_btn_exec'):
            self.loco_btn_exec.setEnabled(True)
        if hasattr(self, 'loco_progress_bar'):
            self.loco_progress_bar.setValue(0)
        if hasattr(self, 'loco_status_label'):
            self.loco_status_label.setText("Ready.")
          
          
    def update_locomotive_ui_state(self):
        count = len(self.locomotive_files)
        if count > 0:
            self.carrier_edit.setText(f"{count} files selected")
        else:
            self.carrier_edit.clear()
            self.carrier_edit.setPlaceholderText("Select multiple PNG images...")
        
        if self.loco_group_box:
            self.loco_group_box.setTitle(f"Selected Files ({count} fragments)")
    
    def remove_specific_file(self, file_path):
        """Remove a specific file from the locomotive list (called by Tile X button)."""
        if file_path in self.locomotive_files:
            self.locomotive_files.remove(file_path)
            # Refresh list to remove the item visually
            self.update_locomotive_list()
            self.update_locomotive_ui_state()
            
    def _add_locomotive_file(self, file_path):
        # Create Tiles
        tile = LocoFileTile(file_path)
        
        # Connect delete signals
        tile.deleteRequested.connect(self.remove_specific_file)

        # Add to Standalone List
        item = QListWidgetItem(self.loco_list_widget)
        item.setSizeHint(QSize(120, 150))
        self.loco_list_widget.addItem(item)
        self.loco_list_widget.setItemWidget(item, tile)
        
            
    def update_locomotive_list(self):
        self.loco_list_widget.clear()
        
        for file_path in self.locomotive_files:
            self._add_locomotive_file(file_path)
                         
    def browse_locomotive_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Multiple PNG Carriers", "", "PNG Images (*.png)"
        )
        if files:
            print(files)
            self.locomotive_files = files
            self.update_locomotive_ui_state()
            self.update_locomotive_list()
            
    def browse_locomotive_files_append(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add PNG Carriers", "", "PNG Images (*.png)"
        )
        if files:
            new_files = [f for f in files if f not in self.locomotive_files]
            if new_files:
                self.locomotive_files.extend(new_files)
                self.update_locomotive_ui_state()
                self.update_locomotive_list()
                
    def switch_to_lsb_mode(self):
        """Switch UI to Standalone Mode (Single Image, Text/Code Files)"""
        
        self.payload_stack.setCurrentIndex(PAGE_PAYLOAD_INPUT)
        
        self.payload_main_group.setTitle("Payload Input")
        
        # 1. Switch Right Panel
        self.preview_stack.setCurrentIndex(PAGE_LSB)
        
        # 2. Configure Carrier Input (Single)
        self.carrier_edit.setPlaceholderText("Select PNG image...")
        
        # 3. Configure Payload Input (Default to Text Tab)
        self.payload_tabs.setCurrentIndex(TAB_INDEX_TEXT)
        
        # 4. Configure Attachment Widget (Restrict to Text/Code files)
        # ใช้ตัวแปร TEXT_FILE_EXTENSIONS ที่ประกาศไว้ข้างบน
        self.attachment_widget.set_allowed_extensions(TEXT_FILE_EXTENSIONS)
        self.attachment_widget.empty_label.setText("Drag & Drop\n(Text files only: .txt, .md, .csv, ...)")
        
        # 5. Reset Standalone View (if exists)
        if hasattr(self, 'standalone_content_stack'):
            self.standalone_content_stack.setCurrentIndex(0)
                    
    def switch_to_locomotive_mode(self):
        """Switch UI to Locomotive Mode (Multiple Images, All File Types)"""
        
        self.payload_main_group.setTitle("Payload Input")
        self.payload_stack.setCurrentIndex(PAGE_PAYLOAD_INPUT)
        
        # 1. Switch Right Panel
        self.preview_stack.setCurrentIndex(PAGE_LOCOMOTIVE)
        
        # 2. Configure Carrier Input (Multiple)
        self.carrier_edit.setPlaceholderText("Select multiple PNG images...")
        
        # 3. Configure Payload Input (Force File Tab)
        self.payload_tabs.setCurrentIndex(TAB_INDEX_FILE)
        
        # 4. Configure Attachment Widget (Allow ALL files)
        self.attachment_widget.set_allowed_extensions(None) 
        self.attachment_widget.empty_label.setText("Drag & Drop\n(All file types)")
        
        # 5. Reset Standalone View (if exists)
        if hasattr(self, 'standalone_content_stack'):
            self.standalone_content_stack.setCurrentIndex(0)
            
    def switch_to_metadata_mode(self):
        self.payload_stack.setCurrentIndex(PAGE_CARRIER_PREVIEW) # แสดงหน้า Preview ฝั่งซ้าย
        self.payload_main_group.setTitle("Carrier Preview")
        self.preview_stack.setCurrentIndex(PAGE_METADATA)
        
        # กำหนด Placeholder
        self.carrier_edit.setPlaceholderText("Select file to edit metadata...")
       
    def browse_metadata_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select File", "", "Media Files (*.jpg *.jpeg *.png *.mp3)"
        )
        if file_path:
            
            self.current_file_path = file_path
            self.carrier_edit.setText(file_path)
            self.update_meta_preview_stats(file_path)
            self.load_file_preview(file_path)
            
            if hasattr(self, 'metadata_editor'):
                self.metadata_editor.load_file(file_path)
        
        

    def on_run_embed(self):
        """
        Main execution handler:
        1. Validates inputs based on selected technique.
        2. Prepares data (UI -> Variables).
        3. Starts the Background Worker Thread.
        """
        
        # [STEP 0] ดึง UI ที่ถูกต้อง (std หรือ loco) เพื่อสั่งงานปุ่มและหลอดโหลด
        ui = self.get_active_ui()
        
        # ตรวจสอบเทคนิคที่เลือก
        current_tech = self.tech_combo.currentText()
        is_LSBPP = "LSB++" in current_tech
        is_locomotive = "Locomotive" in current_tech
        
        # [STEP 1] Validate Cover Source
        if is_LSBPP:
            if not hasattr(self, 'current_file_path') or not self.current_file_path:
                QMessageBox.warning(self, "Missing Input", "Please select a carrier image first!")
                return
        elif is_locomotive:
            if not hasattr(self, 'locomotive_files') or not self.locomotive_files:
                QMessageBox.warning(self, "Missing Input", "Please select at least one PNG carrier image!")
                return

        # [STEP 2] Prepare Payload
        current_tab_index = self.payload_tabs.currentIndex()
        payload_data = None # สำหรับ LSB (ส่งข้อมูลเป็น Text/Bytes)
        payload_path = None # สำหรับ Locomotive (ส่งข้อมูลเป็น Path ไฟล์)
        
        if is_locomotive:
            # Locomotive: บังคับใช้ File Attachment เท่านั้น
            if current_tab_index != TAB_INDEX_FILE:
                 QMessageBox.warning(self, "Input Error", "Locomotive technique requires a file payload (File Attachment tab).")
                 return
            
            payload_path = self.payload_file_path.text()
            if not payload_path or not os.path.exists(payload_path):
                QMessageBox.warning(self, "Missing Input", "Please select a valid payload file!")
                return
        
        else: # LSB++
            if current_tab_index == TAB_INDEX_TEXT:
                # Text Mode
                text_content = self.payload_text.toPlainText()
                if not text_content:
                    QMessageBox.warning(self, "Missing Input", "Please enter a message to embed!")
                    return
                payload_data = text_content 
                
            elif current_tab_index == TAB_INDEX_FILE:
                # File Mode (สำหรับ LSB ต้องอ่านเนื้อไฟล์ออกมา)
                file_path = self.payload_file_path.text()
                if not file_path or not os.path.exists(file_path):
                    QMessageBox.warning(self, "Missing Input", "Please select a valid payload file!")
                    return
                
                try:
                    # อ่านไฟล์เป็น utf-8 string
                    with open(file_path, 'r', encoding='utf-8') as f:
                        payload_data = f.read()
                except Exception as e:
                    QMessageBox.critical(self, "File Error", f"Could not read payload file:\n{str(e)}")
                    return

        # [STEP 3] Prepare Encryption Config
        enc_mode_idx = self.enc_combo.currentIndex()
        is_encrypted = self.encryption_box.isChecked()
        
        mode_str = "none"
        pwd = None
        pub_key_path = None
        
        if is_encrypted:
            if enc_mode_idx == 0: # Password
                mode_str = "password"
                pwd = self.passphrase.text()
                confirm_pwd = self.confirmpassphrase.text()
                
                if not pwd:
                    QMessageBox.warning(self, "Missing Input", "Password cannot be empty!")
                    return
                if pwd != confirm_pwd:
                    QMessageBox.warning(self, "Input Error", "Passwords do not match!")
                    return
                    
            elif enc_mode_idx == 1: # Public Key
                mode_str = "public"
                pub_key_path = self.public_key_edit.text()
                if not pub_key_path or not os.path.exists(pub_key_path):
                    QMessageBox.warning(self, "Missing Input", "Please select a valid Public Key file (.pem)!")
                    return

        # [STEP 4] Update UI State (Disable buttons, Show progress)
        if ui['btn_exec']: 
            ui['btn_exec'].setEnabled(False)
            
        if ui['btn_save']: 
            ui['btn_save'].setEnabled(False)
            ui['btn_save'].hide()
            
        if ui['status']: 
            ui['status'].setText("Initializing...")
            
        if ui['progress']: 
            ui['progress'].setRange(0, 100)
            ui['progress'].setValue(0)
        
        # Update Configurable Editor UI State (แยกตาม tab)
        is_config = hasattr(self, 'mode_combo') and self.mode_combo.currentText() == "Configurable Model"
        if is_config:
            # Initialize embed tab
            if hasattr(self, 'cfg_embed_progress_bar'):
                self.cfg_embed_progress_bar.setValue(0)
            if hasattr(self, 'cfg_embed_status_label'):
                self.cfg_embed_status_label.setText("Initializing...")
            if hasattr(self, 'cfg_embed_btn_exec'):
                self.cfg_embed_btn_exec.setEnabled(False)
            
            # Initialize extract tab
            if hasattr(self, 'cfg_extract_progress_bar'):
                self.cfg_extract_progress_bar.setValue(0)
            if hasattr(self, 'cfg_extract_status_label'):
                self.cfg_extract_status_label.setText("Initializing...")
            if hasattr(self, 'cfg_extract_btn_exec'):
                self.cfg_extract_btn_exec.setEnabled(False)
            
        # [STEP 5] Start Worker
        try:
            if is_LSBPP:
                # กรณี LSB++: ส่ง Single Path + Text Data
                engine = LSBPP()
                self.worker = EmbedWorker(
                    engine=engine,
                    cover_source=self.current_file_path,  # String
                    payload_source=payload_data,           # String Content
                    mode_str=mode_str,
                    pwd=pwd,
                    pub_key=pub_key_path,
                    on_tech='LSB'
                )
            
            elif is_locomotive:
                engine = Locomotive()
                self.worker = EmbedWorker(
                    engine=engine,
                    cover_source=self.locomotive_files,    # List
                    payload_source=payload_path,           # String Path
                    mode_str=mode_str,
                    pwd=pwd,
                    pub_key=pub_key_path,
                    on_tech='Locomotive'
                )

            # เชื่อมต่อ Signals
            self.worker.progress_signal.connect(self.update_progress_ui) 
            self.worker.finished_signal.connect(self.on_embed_finished)
            self.worker.error_signal.connect(self.on_embed_error)
            self.worker.finished.connect(self.worker.deleteLater)

            self.worker.start()

        except Exception as e:
            # กรณี Error ตั้งแต่ยังไม่เริ่ม Thread
            self.on_embed_error(str(e))
            
    # ฟังก์ชันรับค่า Update จาก Worker มาแสดงผลบนจอ
    def update_progress_ui(self, text, percent):
        ui = self.get_active_ui()
        if ui['status']: ui['status'].setText(text)
        if ui['progress']: ui['progress'].setValue(percent)
        
        # Update both tabs when in configurable mode
        is_config = hasattr(self, 'mode_combo') and self.mode_combo.currentText() == "Configurable Model"
        if is_config:
            if hasattr(self, 'cfg_embed_progress_bar'):
                self.cfg_embed_progress_bar.setValue(percent)
            if hasattr(self, 'cfg_embed_status_label'):
                self.cfg_embed_status_label.setText(text)
            if hasattr(self, 'cfg_extract_progress_bar'):
                self.cfg_extract_progress_bar.setValue(percent)
            if hasattr(self, 'cfg_extract_status_label'):
                self.cfg_extract_status_label.setText(text)
        

    # ฟังก์ชันจบงาน (Success Handling)
    def on_embed_finished(self, result_data, metrics):
        """
        ทำงานเมื่อ Worker เสร็จสิ้น
        result_data: 
          - กรณี LSB++: จะเป็น Image Array (numpy array)
          - กรณี Locomotive: จะเป็น Path String (ที่อยู่ไฟล์/โฟลเดอร์)
        """
        ui = self.get_active_ui()
        
        # 1. อัปเดตสถานะหน้าจอ
        if ui['progress']: ui['progress'].setValue(100)
        if ui['status']: ui['status'].setText("Processing Complete.")
        if ui['btn_exec']: ui['btn_exec'].setEnabled(True)
        
        #อัปเดตสถานะหน้าจอ Config page (แยกตาม tab)
        is_config = hasattr(self, 'mode_combo') and self.mode_combo.currentText() == "Configurable Model"
        if is_config:
            # Update embed tab
            if hasattr(self, 'cfg_embed_progress_bar'):
                self.cfg_embed_progress_bar.setValue(100)
            if hasattr(self, 'cfg_embed_status_label'):
                self.cfg_embed_status_label.setText("Processing Complete.")
            if hasattr(self, 'cfg_embed_btn_exec'):
                self.cfg_embed_btn_exec.setEnabled(True)
            if hasattr(self, 'cfg_embed_btn_savestg'):
                self.cfg_embed_btn_savestg.setEnabled(True)
                self.cfg_embed_btn_savestg.show()
                try: self.cfg_embed_btn_savestg.clicked.disconnect()
                except TypeError: pass
                self.cfg_embed_btn_savestg.clicked.connect(
                    lambda: self.on_save_stego(result_data, metrics)
                )
            
            # Update extract tab
            if hasattr(self, 'cfg_extract_progress_bar'):
                self.cfg_extract_progress_bar.setValue(100)
            if hasattr(self, 'cfg_extract_status_label'):
                self.cfg_extract_status_label.setText("Processing Complete.")
            if hasattr(self, 'cfg_extract_btn_exec'):
                self.cfg_extract_btn_exec.setEnabled(True)
            if hasattr(self, 'cfg_extract_btn_savestg'):
                self.cfg_extract_btn_savestg.setEnabled(True)
                self.cfg_extract_btn_savestg.show()
                try: self.cfg_extract_btn_savestg.clicked.disconnect()
                except TypeError: pass
                self.cfg_extract_btn_savestg.clicked.connect(
                    lambda: self.on_save_stego(result_data, metrics)
                )
        
        # 2. จัดการปุ่ม Save
        if ui['btn_save']:
            ui['btn_save'].setEnabled(True)
            ui['btn_save'].show()
            
            # [สำคัญ] ยกเลิกการเชื่อมต่อเก่าก่อน (Disconnect) 
            # เพื่อป้องกันการกดปุ่ม 1 ครั้งแต่ทำงานซ้ำหลายรอบ (Multiple slots)
            try:
                ui['btn_save'].clicked.disconnect()
            except TypeError:
                pass # ถ้ายังไม่เคย Connect ก็ข้ามไป
            
            # 3. เชื่อมต่อปุ่ม Save เข้ากับข้อมูลผลลัพธ์ใหม่
            ui['btn_save'].clicked.connect(
                lambda: self.on_save_stego(result_data, metrics)
            )
        

    # ฟังก์ชันจัดการ Error
    def on_embed_error(self, error_msg):
        ui = self.get_active_ui()
        if ui['status']: ui['status'].setText("Error occurred.")
        if ui['progress']: ui['progress'].setValue(0)
        if ui['btn_exec']: ui['btn_exec'].setEnabled(True)
        
        # Update Configurable Editor Error State (แยกตาม tab)
        is_config = hasattr(self, 'mode_combo') and self.mode_combo.currentText() == "Configurable Model"
        if is_config:
            # Update embed tab
            if hasattr(self, 'cfg_embed_status_label'):
                self.cfg_embed_status_label.setText("Error occurred.")
            if hasattr(self, 'cfg_embed_progress_bar'):
                self.cfg_embed_progress_bar.setValue(0)
            if hasattr(self, 'cfg_embed_btn_exec'):
                self.cfg_embed_btn_exec.setEnabled(True)
            
            # Update extract tab
            if hasattr(self, 'cfg_extract_status_label'):
                self.cfg_extract_status_label.setText("Error occurred.")
            if hasattr(self, 'cfg_extract_progress_bar'):
                self.cfg_extract_progress_bar.setValue(0)
            if hasattr(self, 'cfg_extract_btn_exec'):
                self.cfg_extract_btn_exec.setEnabled(True)
        
        QMessageBox.critical(self, "Embedding Error", error_msg)
        
    def browse_LSB_Cover_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Carrier Image", "", "PNG Images (*.png)"
        )
        if file_path:
            self.current_file_path = file_path
            self.carrier_edit.setText(file_path)
            self.load_image_preview(file_path)    
            payload_size = self.update_payload_size()
            self.update_lsb_preview_stats(file_path, payload_size)
            self.update_capacity_indicator()
            
            self.start_capacity_calculation(file_path)
            
            
    def update_payload_size(self):
        return len(self.payload_text.toPlainText().encode()) if hasattr(self, 'payload_text') else 0
    
    def load_file_preview(self, file_path):
        # กำหนดกลุ่มนามสกุลไฟล์
        image_exts = ('.png', '.jpg', '.jpeg')
        audio_exts = ('.mp3', '.wav')

        if file_path.lower().endswith(image_exts):
            # CASE 1: รูปภาพ
            pixmap = QPixmap(file_path)
            self.original_meta_preview_pixmaps = pixmap
            
            if not pixmap.isNull():
                self.update_meta_preview_scaling(pixmap, self.meta_preview_label)

        elif file_path.lower().endswith(audio_exts):
            # CASE 2: ไฟล์เสียง
            
            # 1. เคลียร์รูปต้นฉบับเดิม
            self.original_meta_preview_pixmaps = None 

            # 2. สร้างไอคอน
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume)
            icon_pixmap = icon.pixmap(64, 64)
            
            # --- จุดที่แก้ไข ---
            # ต้องสั่งที่ meta_preview_label ไม่ใช่ self
            self.meta_preview_label.setPixmap(icon_pixmap)
            self.meta_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.meta_preview_label.setToolTip(f"Audio File: {os.path.basename(file_path)}")

        else:
            # กรณีไฟล์อื่นๆ
            self.meta_preview_label.setText(f"File not supported:\n{os.path.basename(file_path)}")
            self.original_meta_preview_pixmaps = None
      
    def load_image_preview(self, image_path):
        pixmap = QPixmap(image_path)
        self.original_lsb_preview_pixmaps = pixmap
        
        if not pixmap.isNull():
            self.update_preview_scaling(pixmap, self.preview_label)
            
    def update_preview_scaling(self, original_preview_pixmaps, preview_label):
        """Update all preview labels with proper scaling based on current size."""
        # 1. เช็คก่อนว่ามีรูปภาพให้ประมวลผลไหม (กัน Crash)
        pixmap = original_preview_pixmaps
        if pixmap is None or pixmap.isNull():
            return

        # 2. คำนวณขนาด
        label_width = preview_label.width() - 20 
            
        max_height = preview_label.height() - 20 
        
        # 3. ประมวลผลภาพ
        scaled_pixmap = pixmap.scaled(
            label_width, max_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        # 4. อัปเดต UI 
        preview_label.setPixmap(scaled_pixmap)
        
    def update_meta_preview_scaling(self, original_preview_pixmaps, preview_label):
        """Update all preview labels with proper scaling based on current size."""
        # 1. เช็คก่อนว่ามีรูปภาพให้ประมวลผลไหม (กัน Crash)
        pixmap = original_preview_pixmaps
        if pixmap is None or pixmap.isNull():
            return

        # 2. คำนวณขนาด
        label_width = preview_label.width() - 20
        label_height = preview_label.height() -20
        
        
        # 3. ประมวลผลภาพ
        scaled_pixmap = pixmap.scaled(
            label_width, label_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        # 4. อัปเดต UI 
        preview_label.setPixmap(scaled_pixmap)
        
        
            
    def create_left_panel(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_area.setMinimumWidth(350)
        scroll_area.setMaximumWidth(550)
        
        widget = QWidget()
        widget.setMinimumWidth(350)
        
        layout = QVBoxLayout(widget)
        layout.setSpacing(6)
        layout.setContentsMargins(4, 4, 4, 4)
        
        layout.addWidget(self.build_mode_section())
        layout.addWidget(self.build_technique_section())
        layout.addWidget(self.build_carrier_section())
        layout.addWidget(self.build_payload_section(), 1)
        layout.addWidget(self.build_encryption_section())
        layout.addStretch()
        
        scroll_area.setWidget(widget)
        return scroll_area
    
    # Components(Groupbox) of left panel
    def build_mode_section(self):
        return self.create_combo_group("Mode Selection", [
            (
                "Standalone", 
                "Hide data using one specific method independently."
            ),
            (
                "Configurable Model", 
                "Create a custom process by combining multiple techniques."
            )
        ], "mode_combo")

    def build_technique_section(self):
        return self.create_combo_group("Technique Selection", [
            (
            "LSB++", 
            "Hides data in PNG pixels using an adaptive LSB algorithm with password-based distribution."
            ),
            (
            "Locomotive", 
            "Hides data by fragmenting and appending it across the end-of-file of multiple PNGs."
            ),
            (
            "Metadata", 
            "Hides messages within PNG text chunks or MP3 tags"
            )
        ], "tech_combo")
    
    def create_combo_group(self, title, items, attribute_name):
        box = QGroupBox(title)
        box.setMinimumHeight(70)
        box.setMaximumHeight(85)
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 12, 6, 6)
        layout.setSpacing(4)
        combo = QComboBox()

        for item in items:
            if isinstance(item, (list, tuple)):
                name = item[0]
                hint = item[1] if len(item) > 1 else None
            else:
                name = item
                hint = None
                
            combo.addItem(name)
            current_index = combo.count() - 1
            
            if hint:
                combo.setItemData(current_index, hint, Qt.ItemDataRole.ToolTipRole)
            
        setattr(self, attribute_name, combo)
        # combo.currentIndexChanged.connect(self.on_technique_changed)
        
        if attribute_name == "mode_combo":
            combo.currentIndexChanged.connect(self.on_mode_changed)
        else:
            combo.currentIndexChanged.connect(self.on_technique_changed)


        layout.addWidget(combo)
        box.setLayout(layout)
        return box
        
    def build_carrier_section(self):
            box = QGroupBox("Select Carrier File")
            box.setMinimumHeight(75)
            box.setMaximumHeight(90)
            
            layout = QHBoxLayout() 
            layout.setContentsMargins(6, 12, 6, 6)
            layout.setSpacing(6)
            
            self.carrier_edit = QLineEdit()
            self.carrier_edit.setReadOnly(True)
            self.carrier_edit.setPlaceholderText("Select PNG Image...")
            
            self.carrier_browse_btn = QPushButton("Browse")
            
            layout.addWidget(self.carrier_edit)
            layout.addWidget(self.carrier_browse_btn)
            
            box.setLayout(layout)
            return box
    
    def build_payload_section(self):
        box = QGroupBox("Payload Input")
        self.payload_main_group = box
        box.setMinimumHeight(200)
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 12, 6, 6)
        layout.setSpacing(4)
        
        self.payload_stack = QStackedWidget()
        self.payload_stack.addWidget(self.create_standard_payload_page())
        self.payload_stack.addWidget(self.create_metadata_preview_page())
        
        
        size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        size_policy.setVerticalStretch(1)
        self.payload_stack.setSizePolicy(size_policy)
        
        layout.addWidget(self.payload_stack, 1)
        box.setLayout(layout)
        return box
    
    def create_metadata_preview_page(self):
        """Preview section with stats display (for Metadata mode)"""
        # 1. เปลี่ยนจาก QGroupBox เป็น QWidget ธรรมดา
        container = QWidget()
        
        # 2. สร้าง Layout และผูกกับ container เลย
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        
        # Preview Label with drag-and-drop support (ส่วนเดิม)
        self.meta_preview_label = DraggablePreviewLabel(allowed_extensions=['.jpg', '.png', '.mp3'])
        self.meta_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.meta_preview_label.setText("No File Selected\n\ndrag & drop file (JPG, PNG, MP3) here")
        self.meta_preview_label.setStyleSheet("""
            QLabel {
                border: 2px dashed #555;
                background-color: #222;
                color: #888;
                font-size: 10pt;
            }
        """)
        self.meta_preview_label.setMinimumHeight(200)
        self.meta_preview_label.setScaledContents(False)
        
        self.meta_preview_label.file_dropped.connect(self.on_meta_preview_file_dropped)
        
        layout.addWidget(self.meta_preview_label, 1)
        
        # Info Label (file info) (ส่วนเดิม)
        preview_info_label = QLabel("")
        preview_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_info_label.setStyleSheet("color: #e0e0e0; font-size: 9pt;")
        preview_info_label.hide()
        setattr(self, "preview_info_label", preview_info_label)
        
        layout.addWidget(preview_info_label, 0)
        
        # Stats Row (below preview) (ส่วนเดิม)
        stats_container = self.build_metadata_preview_stats()
        layout.addWidget(stats_container, 0)
        
        return container
    
    def build_metadata_preview_stats(self):
        """Build stats display row"""
        container = QWidget()
        container.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px;
            }
        """)
        
        layout = QHBoxLayout(container)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(8)
        
        
        # File Name Stat
        self.meta_stat_filename = self.create_stat_item("File:", "None", "#e0e0e0")
        layout.addWidget(self.meta_stat_filename)
        
        # Image Size Stat
        self.meta_stat_image_size = self.create_stat_item("Size:", "0 B", "#e0e0e0")
        layout.addWidget(self.meta_stat_image_size)
        
         
        return container
    
    
    def create_standard_payload_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.payload_tabs = QTabWidget()
        self.payload_tabs.addTab(self.create_text_payload_tab(), "Text Message")
        self.payload_tabs.addTab(self.create_file_payload_tab(), "File Attachment")
        
        layout.addWidget(self.payload_tabs)
        return page
    
    def create_text_payload_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(4)
            
            self.payload_text = QTextEdit()
            self.payload_text.setPlaceholderText("Enter secret message here...")
            
            # toolbar: text editor & capacity text
            toolbar = QHBoxLayout()
            toolbar.setSpacing(4)
            btn_editor = QPushButton("Text Editor")
            btn_editor.setMinimumSize(100, 25)
            btn_editor.setStyleSheet("font-size: 8pt; padding: 2px;")
            btn_editor.clicked.connect(self.open_text_editor)
            
            self.lbl_capacity = QLabel("Size: 0 B")
            self.lbl_capacity.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.lbl_capacity.setStyleSheet("color: #aaa;  font-size: 8pt;")
            
            toolbar.addWidget(btn_editor)
            toolbar.addStretch()
            toolbar.addWidget(self.lbl_capacity)
        
            layout.addWidget(self.payload_text, 1)
            layout.addLayout(toolbar, 0)
            
            self.payload_text.textChanged.connect(self.update_capacity_indicator)
            
            # self.payload_text.textChanged.connect(self._on_payload_changed)
            
            return tab
    
    def create_file_payload_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 10, 5, 10)  # Balanced top/bottom spacing
        layout.setSpacing(6)
        
        self.payload_file_path = QLineEdit()
        self.payload_file_path.setPlaceholderText("Path to secret file...")
        self.payload_file_path.hide()
        
        self.attachment_widget = AttachmentDropWidget()
        self.attachment_widget.fileSelected.connect(self.on_file_attach_selected)
        self.attachment_widget.fileCleared.connect(self.payload_file_path.clear)

        self.attachment_widget.requestBrowse.connect(self.browse_payload_file)

        # Default hint: prefer text-mode files for File Attachment techniques
        try:
            self.attachment_widget.empty_label.setText("Drag & Drop\n(Text files only: .txt, .md, .csv, ...)")
        except Exception:
            pass

        layout.addWidget(self.attachment_widget, 1)
        layout.addWidget(self.payload_file_path, 0)
        
        return tab
                    
    # ========================================================================
    # CAPACITY & TEXT EDITOR
    # ========================================================================
            
    def update_capacity_indicator(self):
        """คำนวณขนาดและแสดงสถานะ 3 ระดับ"""
        if not hasattr(self, 'payload_text'): return

        # 1. หาขนาด Payload ปัจจุบัน
        text_bytes = self.payload_text.toPlainText().encode('utf-8')
        current_size = len(text_bytes)
        
        # 2. ดึงค่า Limit
        safe_cap = getattr(self, 'limit_safe', 0)
        max_cap = getattr(self, 'limit_max', 0)
        
        if max_cap == 0 and safe_cap == 0:
            # กรณีไม่มีภาพ หรือภาพเล็กเกินเยียวยาจริงๆ
            self.lbl_capacity.setText(f"Size: {format_file_size(current_size)}")
            self.lbl_capacity.setStyleSheet("color: #aaa; font-size: 8pt;")
            self.update_payload_size()
            return

        # ==========================================================
        # [CRITICAL FIX] เปลี่ยนตัวหารจาก safe_cap เป็น max_cap
        # ==========================================================
        # เดิม: ... / {format_file_size(safe_cap)}  <-- สาเหตุที่โชว์ 0 B
        # ใหม่: ... / {format_file_size(max_cap)}   <-- จะโชว์ 28 B ตามต้องการ
        
        cap_text = f"Capacity: {format_file_size(current_size)} / {format_file_size(max_cap)}"
        
        # 4. ตรวจสอบเงื่อนไข 3 ระดับ (Logic สีถูกต้องแล้ว)
        if current_size <= safe_cap:
            # SAFE (สีเทา)
            self.lbl_capacity.setStyleSheet("color: #aaa; font-size: 8pt;")
            self.lbl_capacity.setToolTip("Safe: Optimal payload size. Ready to embed.")
            
        elif current_size <= max_cap:
            # RISK (สีส้ม) - Password Mode ใช้ได้
            self.lbl_capacity.setStyleSheet("color: #ffaa00; font-weight: bold; font-size: 8pt;")
            self.lbl_capacity.setToolTip("Risk: Large payload. Public Key embedding may fail")
            
        else:
            # IMPOSSIBLE (สีแดง)
            self.lbl_capacity.setStyleSheet("color: #ff5555; font-weight: bold; font-size: 8pt;")
            self.lbl_capacity.setToolTip("Over Limit: Capacity exceeded. Cannot embed.")
            
        self.lbl_capacity.setText(cap_text)
        self.update_payload_size()
            
    def start_capacity_calculation(self, image_path):
        """สั่งเริ่มคำนวณความจุใน Background"""
        # ตั้งค่า UI ให้รู้ว่ากำลังคิดอยู่
        if hasattr(self, 'stat_capacity'):
            self.lbl_capacity.setText("Calculating...")
            self.lbl_capacity.setStyleSheet("color: #aaa; font-size: 8pt;")
            self.stat_capacity.value_label.setText("Calculating...")
        
        # หยุด Worker เก่าถ้าทำงานอยู่ (กัน Race Condition กรณีเปลี่ยนรูปเร็วๆ)
        if hasattr(self, 'cap_worker') and self.cap_worker.isRunning():
            self.cap_worker.terminate()
            self.cap_worker.wait()

        # สร้างและเริ่ม Worker ใหม่
        self.cap_worker = CapacityWorker(image_path)
        self.cap_worker.finished_signal.connect(self._on_capacity_computed)
        self.cap_worker.start()

    def _on_capacity_computed(self, safe_bytes, max_bytes):
        """รับค่าความจุมาเก็บไว้ทั้ง 2 ระดับ"""
        self.limit_safe = safe_bytes
        self.limit_max = max_bytes
        
        self.update_capacity_indicator()
        
        # Update Stats (ซ้ายมือ) 
        if hasattr(self, 'stat_capacity'):
             # เปลี่ยน Label ให้สื่อความหมายชัดเจน
             self.stat_capacity.findChild(QLabel).setText("Max Capacity:") 
             # โชว์ค่า Max (28 B) แทน Safe (0 B)
             self.stat_capacity.value_label.setText(format_file_size(max_bytes))

    def open_text_editor(self):
        current_text = self.payload_text.toPlainText()
        
        # ดึงค่า Limit ที่คำนวณไว้จาก CapacityWorker (ถ้าไม่มีให้เป็น 0)
        safe_cap = getattr(self, 'limit_safe', 0)
        max_cap = getattr(self, 'limit_max', 0)
        
        # ส่ง safe_limit และ max_limit เข้าไปใน Dialog
        dialog = TextEditorDialog(
            initial_text=current_text, 
            safe_limit=safe_cap, 
            max_limit=max_cap, 
            parent=self
        )
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.payload_text.setPlainText(dialog.get_text())
            
    # ========================================================================
    # FILE SELECTION HANDLERS
    # ========================================================================
    
    def on_file_attach_selected(self, file_path):
        """Handle file selection from drag-drop (called by signal from AttachmentDropWidget)"""
        # NOTE: This is ONLY called when user drags a file, NOT when browsing
        
        self.payload_file_path.setText(file_path)
        
        current_tech = self.tech_combo.currentText()
        is_locomotive = "Locomotive" in current_tech
        
        # Extract text content for LSB++ mode
        if not is_locomotive:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in TEXT_FILE_EXTENSIONS:
                try:
                    # Simple read with UTF-8
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self.payload_text.setPlainText(content)
                    self.payload_tabs.setCurrentIndex(TAB_INDEX_TEXT)
                    self.update_capacity_indicator()
                except UnicodeDecodeError:
                    # Try other common encodings
                    for encoding in ['utf-16', 'latin-1', 'cp1252']:
                        try:
                            with open(file_path, 'r', encoding=encoding) as f:
                                content = f.read()
                            self.payload_text.setPlainText(content)
                            self.payload_tabs.setCurrentIndex(TAB_INDEX_TEXT)
                            self.update_capacity_indicator()
                            break
                        except:
                            continue
                except Exception as e:
                    print(f"Error reading file: {e}")

    def on_public_key_selected(self, file_path):
        """Handler for when a public-key file is selected in the attachment widget."""
        self.public_key_edit.setText(file_path)

    def browse_public_key(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Public Key", "", "PEM Files (*.pem);;All Files (*)"
        )
        if file_path:
            # Update both the read-only path field and the attachment widget
            self.public_key_edit.setText(file_path)
            if hasattr(self, 'pubkey_attachment'):
                try:
                    self.pubkey_attachment.set_file(file_path)
                except Exception:
                    pass
    
    def browse_payload_file(self):
        current_tech = self.tech_combo.currentText()
        is_locomotive = "Locomotive" in current_tech

        if is_locomotive:
            file_filter = "All Files (*)"
            caption = "Select Secret File (Any Type)"
        else:
            # Expanded file filters for LSB++ mode
            file_filter = (
                "Text Files (*.txt *.md *.csv *.json *.xml *.log);;"
                "Code Files (*.py *.js *.ts *.java *.cpp *.c *.h *.cs *.go *.rs);;"
                "Config Files (*.yml *.yaml *.toml *.ini *.conf *.cfg *.env);;"
                "Web Files (*.html *.css *.scss *.jsx *.tsx *.vue);;"
                "Script Files (*.sql *.sh *.bat *.ps1);;"
                "All Files (*)"
            )
            caption = "Select Secret Text File"

        file_path, _ = QFileDialog.getOpenFileName(self, caption, "", file_filter)
        
        if file_path:
            # Set file in attachment widget (this is the ONLY place we call set_file from browse)
            if hasattr(self, 'attachment_widget'):
                self.attachment_widget.set_file(file_path)
            
            self.payload_file_path.setText(file_path)
            
            # Extract text content for LSB++ mode
            if not is_locomotive:
                ext = os.path.splitext(file_path)[1].lower()
                if ext in TEXT_FILE_EXTENSIONS:
                    try:
                        # Simple read with UTF-8
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        self.payload_text.setPlainText(content)
                        self.payload_tabs.setCurrentIndex(TAB_INDEX_TEXT)
                        self.update_capacity_indicator()
                    except UnicodeDecodeError:
                        # Try other common encodings
                        for encoding in ['utf-16', 'latin-1', 'cp1252']:
                            try:
                                with open(file_path, 'r', encoding=encoding) as f:
                                    content = f.read()
                                self.payload_text.setPlainText(content)
                                self.payload_tabs.setCurrentIndex(TAB_INDEX_TEXT)
                                self.update_capacity_indicator()
                                break
                            except:
                                continue
                    except Exception as e:
                        print(f"Error reading file: {e}")
                        
    def build_encryption_section(self):
        self.encryption_box = QGroupBox("Encryption Options")
        self.encryption_box.setCheckable(True)
        self.encryption_box.setChecked(True)
        self.encryption_box.setMinimumHeight(160)
        self.encryption_box.setMaximumHeight(190)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 12, 6, 6)
        layout.setSpacing(6)
        
        tt = Qt.ItemDataRole.ToolTipRole
        type_row = QHBoxLayout()
        self.lbl_key = QLabel("Key Type:")
        self.enc_combo = QComboBox()
        self.enc_combo.addItem("Password (AES-256)", "password")
        self.enc_combo.addItem("Public Key (RSA-3072)", "public")
        self.enc_combo.setItemData(0, "Use a passphrase to encrypt the payload", tt)
        self.enc_combo.setItemData(1, "Use RSA public key to encrypt the payload", tt)
        
        self.enc_combo.currentIndexChanged.connect(self.toggle_encryption_inputs)
        type_row.addWidget(self.lbl_key)
        type_row.addWidget(self.enc_combo)
        layout.addLayout(type_row)

        self.enc_stack = QStackedWidget()
        self.enc_stack.addWidget(self.create_password_page())
        self.enc_stack.addWidget(self.create_public_key_page())
        
        layout.addWidget(self.enc_stack)
        self.encryption_box.setLayout(layout)
        
        self.encryption_box.toggled.connect(self.enc_combo.setEnabled)
        self.encryption_box.toggled.connect(self.enc_stack.setEnabled)
        
        return self.encryption_box
    
    def toggle_encryption_inputs(self):
        self.enc_stack.setCurrentIndex(self.enc_combo.currentIndex())
        
    def create_password_page(self):
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_pass = QLabel("Password:")
        self.passphrase = QLineEdit()
        self.passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.passphrase.setPlaceholderText("Enter Passphrase...")
        self.add_visibility_toggle(self.passphrase)
        
        self.lbl_confirm = QLabel("Confirm:")
        self.confirmpassphrase = QLineEdit()
        self.confirmpassphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirmpassphrase.setPlaceholderText("Confirm Passphrase...")
        self.add_visibility_toggle(self.confirmpassphrase)

        layout.addWidget(self.lbl_pass, 0, 0)
        layout.addWidget(self.passphrase, 0, 1)
        layout.addWidget(self.lbl_confirm, 1, 0)
        layout.addWidget(self.confirmpassphrase, 1, 1)
        
        return page
    
    def add_visibility_toggle(self, line_edit):
        """Add eye icon toggle using programmatic drawing"""
        
        def create_eye_icon(is_open):
            pixmap = QPixmap(24, 24)
            pixmap.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Setup Pen & Color
            color = QColor("#888888")
            pen = QPen(color, 2)
            painter.setPen(pen)
            
            if is_open:
                # Draw Open Eye (Oval + Pupil)
                painter.drawEllipse(2, 6, 20, 12) # Outer eye
                painter.setBrush(color)           # Fill pupil
                painter.drawEllipse(10, 10, 4, 4) # Pupil
            else:
                # Draw Closed Eye (Oval + Slash)
                painter.drawEllipse(2, 6, 20, 12) # Outer eye
                # Draw slash line
                painter.drawLine(4, 4, 20, 20)
                
            painter.end()
            return QIcon(pixmap)

        icon_visible = create_eye_icon(True)
        icon_hidden = create_eye_icon(False)

        # Default state: Password hidden -> Show "Hidden" icon (Closed Eye)
        action = line_edit.addAction(icon_hidden, QLineEdit.ActionPosition.TrailingPosition)
        
        def toggle():
            is_password = line_edit.echoMode() == QLineEdit.EchoMode.Password
            if is_password:
                # Show Text -> Show "Open Eye"
                line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
                action.setIcon(icon_visible)
            else:
                # Hide Text -> Show "Closed Eye"
                line_edit.setEchoMode(QLineEdit.EchoMode.Password)
                action.setIcon(icon_hidden)
                
        action.triggered.connect(toggle)
    
    def create_public_key_page(self):
        page = QWidget()
        layout = QVBoxLayout(page) 
        layout.setContentsMargins(0, 0, 0, 0)

        self.public_key_edit = QLineEdit()
        self.public_key_edit.setPlaceholderText("Path to public key...")
        self.public_key_edit.hide()
        layout.addWidget(self.public_key_edit) 

        # Attachment widget for public key (accept .pem by default)
        self.pubkey_attachment = AttachmentDropWidget(allowed_extensions='.pem')
        
        try:
            self.pubkey_attachment.empty_label.setText("Import Public Key\n(.pem files)")
        except Exception:
            pass

        self.pubkey_attachment.requestBrowse.connect(self.browse_public_key)
        self.pubkey_attachment.fileSelected.connect(self.on_public_key_selected)

        layout.addWidget(self.pubkey_attachment)

        return page
    
    def create_right_panel(self):

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)

        # ===== Splitter =====
        splitter = QSplitter(Qt.Orientation.Vertical)

        # ----- Preview (TOP) -----
        self.preview_stack = self.create_preview_area()
        splitter.addWidget(self.preview_stack)

        # ----- Config Editor (BOTTOM) -----
        self.config_editor = self.create_config_editor()
        self.config_editor.setVisible(False)
        splitter.addWidget(self.config_editor)

        # Initial size ratio
        splitter.setSizes([500, 200])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

        return panel
    
    def create_config_editor(self):
        box = QGroupBox("Configurable Editor")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(6, 12, 6, 6)
        layout.setSpacing(6)

        # =====================================================
        # Top Toolbar: Template Selector + Import/Export
        # =====================================================
        top_toolbar = QHBoxLayout()
        top_toolbar.setSpacing(8)
        
        # Template Selector Label
        lbl_template = QLabel("Template:")
        lbl_template.setStyleSheet("color: #ccc; font-size: 9pt; font-weight: bold;")
        top_toolbar.addWidget(lbl_template)
        
        # Template Dropdown
        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(200)
        self.template_combo.setFixedHeight(26)
        self.template_combo.addItem("-- Custom (Design Your Own) --")
        self.template_combo.addItem("Basic: LSB++ → Encryption")
        self.template_combo.addItem("Advanced: LSB++ → Locomotive → Encryption")
        self.template_combo.addItem("Stealth: LSB++ → Metadata → Encryption")
        self.template_combo.addItem("Maximum Security: Triple Layer + Encryption")
        self.template_combo.setToolTip("Select a pre-designed embedding template or create your own")
        self.template_combo.currentIndexChanged.connect(self._on_template_selected)
        
        top_toolbar.addWidget(self.template_combo)
        top_toolbar.addStretch()
        
        # Import Button
        btn_import = QPushButton("Import Config")
        btn_import.setFixedHeight(26)
        btn_import.setMinimumWidth(100)
        btn_import.setStyleSheet("""
            QPushButton {
                background-color: #4a5a3a;
                border: 1px solid #5a6a4a;
                border-radius: 3px;
                color: white;
                font-size: 9pt;
                padding: 2px 8px;
            }
            QPushButton:hover {
                background-color: #5a6a4a;
                color: white;
            }
            QPushButton:disabled {
                background-color: #333;
                color: #666;
            }
        """)
        btn_import.setEnabled(True)  # เตรียมไว้อนาคต
        btn_import.setToolTip("Import pipeline configuration from JSON file (Coming Soon)")
        btn_import.clicked.connect(self._import_pipeline_config)
        
        # Export Button
        btn_export = QPushButton("Export Config")
        btn_export.setFixedHeight(26)
        btn_export.setMinimumWidth(100)
        btn_export.setStyleSheet("""
            QPushButton {
                background-color: #3a5a6a;
                border: 1px solid #4a6a7a;
                border-radius: 3px;
                color: white;
                font-size: 9pt;
                padding: 2px 8px;
            }
            QPushButton:hover {
                background-color: #4a6a8a;
            }
        """)
        btn_export.setToolTip("Export current pipeline configuration to JSON file")
        btn_export.clicked.connect(self._export_pipeline_config)
        
        top_toolbar.addWidget(btn_import)
        top_toolbar.addWidget(btn_export)
        
        layout.addLayout(top_toolbar)
        
        # Separator Line
        line = QWidget()
        line.setFixedHeight(1)
        # line.setStyleSheet("background-color: #555;")
        layout.addWidget(line)

        # =====================================================
        # Tab Widget
        # =====================================================
        self.pipeline_tabs = QTabWidget()
        self.pipeline_tabs.addTab(self.build_config_editor_tab("embed"), "Embed Pipeline")
        self.pipeline_tabs.addTab(self.build_config_editor_tab("extract"), "Extract Pipeline")

        layout.addWidget(self.pipeline_tabs)
        return box
    
    def _on_template_selected(self, index):
        """Handle template selection from dropdown"""
        if index == 0:
            # Custom - do nothing, let user design
            return
        
        # Clear existing pipeline
        reply = QMessageBox.question(
            self,
            "Load Template",
            f"This will clear your current pipeline and load the selected template.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.No:
            # Reset to "Custom"
            self.template_combo.setCurrentIndex(0)
            return
        
        # Clear current pipeline
        self._clear_all_pipelines()
        
        # Load template based on selection
        if index == 1:
            # Basic: LSB++ → Encryption
            self._load_template_basic()
        elif index == 2:
            # Advanced: LSB++ → Locomotive → Encryption
            self._load_template_advanced()
        elif index == 3:
            # Stealth: LSB++ → Metadata → Encryption
            self._load_template_stealth()
        elif index == 4:
            # Maximum Security: Triple Layer + Encryption
            self._load_template_max_security()
        
        # Reset to Custom after loading
        self.template_combo.setCurrentIndex(0)


    def _load_template_basic(self):
        """Load Basic template: LSB++ with encryption"""
        # Set technique to LSB++
        self.tech_combo.setCurrentIndex(0)  # Assuming LSB++ is first
        # Enable encryption
        self.encryption_box.setChecked(True)
        # Commit to pipeline
        self.commit_stego_config()
        
        QMessageBox.information(
            self,
            "Template Loaded",
            "Basic template loaded:\n• LSB++ (Encrypted)"
        )


    def _load_template_advanced(self):
        """Load Advanced template: LSB++ → Locomotive"""
        # Example implementation - adjust based on your technique indices
        techniques = [
            ("LSB++", True),      # (technique_name, encrypted)
            ("Locomotive", True)
        ]
        
        for tech_name, encrypted in techniques:
            # Find technique index
            for i in range(self.tech_combo.count()):
                if tech_name in self.tech_combo.itemText(i):
                    self.tech_combo.setCurrentIndex(i)
                    self.encryption_box.setChecked(encrypted)
                    self.commit_stego_config()
                    break
        
        QMessageBox.information(
            self,
            "Template Loaded",
            "Advanced template loaded:\n• LSB++ (Encrypted)\n• Locomotive (Encrypted)"
        )


    def _load_template_stealth(self):
        """Load Stealth template: LSB++ → Metadata"""
        QMessageBox.information(
            self,
            "Template",
            "Stealth template (LSB++ → Metadata) - Implementation pending"
        )


    def _load_template_max_security(self):
        """Load Maximum Security template: Triple layer"""
        QMessageBox.information(
            self,
            "Template",
            "Maximum Security template - Implementation pending"
        )


    def _import_pipeline_config(self):
        """Import pipeline configuration from JSON file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Pipeline Configuration",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validate structure
            if "version" not in data or "embed_pipeline" not in data:
                raise ValueError("Invalid configuration file format")
            
            # Clear and load
            self._clear_all_pipelines()
            
            self.embed_pipeline = data.get("embed_pipeline", [])
            self.extract_pipeline = data.get("extract_pipeline", [])
            
            # Rebuild UI
            self.embed_list.clear()
            self.extract_list.clear()
            
            for step in self.embed_pipeline:
                self._add_list_item(self.embed_list, step["display"], step["id"])
            
            for step in self.extract_pipeline:
                self._add_list_item(self.extract_list, step["display"], step["id"])
            
            self._update_step_labels(self.embed_list)
            self._update_step_labels(self.extract_list)
            
            QMessageBox.information(
                self,
                "Import Successful",
                f"Pipeline configuration imported from:\n{file_path}"
            )
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Import Error",
                f"Failed to import configuration:\n{e}"
            )
    
    def build_config_editor_tab(self, tab_type):

            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            tab_layout.setContentsMargins(4, 4, 4, 4)
            tab_layout.setSpacing(4)

            # ---------------- LIST ----------------
            list_widget = QListWidget()
            list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

            if tab_type == "embed":
                self.embed_list = list_widget
            else:
                self.extract_list = list_widget

            tab_layout.addWidget(list_widget, 1)

            # =====================================================
            # BUTTON ROW  (แยกตาม tab type)
            # =====================================================
            btn_row = QHBoxLayout()
            btn_row.setSpacing(6)

            # -------- ACTION BUTTONS (แยกตาม tab) --------
            if tab_type == "embed":
                btn_exec = QPushButton("Embed Data")
                setattr(self, "cfg_embed_btn_exec", btn_exec)
                
                btn_guide = QPushButton("GuideNote")
                setattr(self, "cfg_embed_btn_guide", btn_guide)
                
                btn_savestg = QPushButton("Save Stego")
                setattr(self, "cfg_embed_btn_savestg", btn_savestg)
            else:
                btn_exec = QPushButton("Embed Data")
                setattr(self, "cfg_extract_btn_exec", btn_exec)
                
                btn_guide = QPushButton("GuideNote")
                setattr(self, "cfg_extract_btn_guide", btn_guide)
                
                btn_savestg = QPushButton("Save Stego")
                setattr(self, "cfg_extract_btn_savestg", btn_savestg)

            btn_exec.setStyleSheet("font-weight:bold;background:#2d5a75;")
            btn_savestg.setStyleSheet("font-weight:bold;background:#3d7a4d;")
            btn_savestg.setEnabled(False)
            btn_savestg.hide()

            btn_exec.clicked.connect(self.on_run_embed)

            btn_guide.clicked.connect(
                lambda: QMessageBox.information(
                    self,
                    "Guide",
                    "GuideNote editor not implemented yet."
                )
            )

            btn_row.addWidget(btn_exec)
            btn_row.addWidget(btn_guide)
            btn_row.addWidget(btn_savestg)
            btn_row.addSpacing(12)

            # -------- MOVE --------
            btn_up = QPushButton("Up")
            btn_down = QPushButton("Down")

            btn_up.clicked.connect(
                lambda: self._move_pipeline_item(list_widget, -1)
            )
            btn_down.clicked.connect(
                lambda: self._move_pipeline_item(list_widget, 1)
            )

            btn_row.addWidget(btn_up)
            btn_row.addWidget(btn_down)
            btn_row.addSpacing(12)

            # -------- MANAGE --------
            btn_remove = QPushButton("Remove")
            btn_clear = QPushButton("Clear All")

            btn_clear.setStyleSheet("background:#552d2d;")

            if tab_type == "embed":
                btn_remove.clicked.connect(self._remove_from_embed_pipeline)
                btn_clear.clicked.connect(self._clear_all_pipelines)
            else:
                btn_remove.clicked.connect(self._remove_from_extract_pipeline)
                btn_clear.clicked.connect(self._clear_extract_pipeline)

            btn_row.addWidget(btn_remove)
            btn_row.addWidget(btn_clear)

            tab_layout.addLayout(btn_row)

            # =====================================================
            # PROGRESS SECTION (แยกตาม tab)
            # =====================================================
            if tab_type == "embed":
                progress_bar = QProgressBar()
                progress_bar.setTextVisible(False)
                progress_bar.setRange(0, 100)
                progress_bar.setValue(0)
                progress_bar.setFixedHeight(6)
                setattr(self, "cfg_embed_progress_bar", progress_bar)

                status_label = QLabel("Ready.")
                status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                status_label.setStyleSheet("color:#888;font-size:9pt;")
                setattr(self, "cfg_embed_status_label", status_label)
            else:
                progress_bar = QProgressBar()
                progress_bar.setTextVisible(False)
                progress_bar.setRange(0, 100)
                progress_bar.setValue(0)
                progress_bar.setFixedHeight(6)
                setattr(self, "cfg_extract_progress_bar", progress_bar)

                status_label = QLabel("Ready.")
                status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                status_label.setStyleSheet("color:#888;font-size:9pt;")
                setattr(self, "cfg_extract_status_label", status_label)

            tab_layout.addWidget(progress_bar)
            tab_layout.addWidget(status_label)

            return tab

    # ========================================================================
    # CONFIGURABLE EDITOR: Pipeline helpers and commit
    # ========================================================================

    def _add_list_item(self, list_widget, text, uid):
        """Add item to list with user role id for pipeline sync."""
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, uid)
        list_widget.addItem(item)

    def _update_step_labels(self, list_widget):
        """Update list items to show Step N: prefix."""
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            text = item.text()
            if text.startswith("Step "):
                parts = text.split(":", 1)
                if len(parts) == 2:
                    text = parts[1].strip()
            item.setText(f"Step {i + 1}: {text}")

    def _move_pipeline_item(self, list_widget, direction):
        """Move selected item up (-1) or down (+1); sync pipeline data."""
        row = list_widget.currentRow()
        if row < 0:
            return
        new_row = row + direction
        if new_row < 0 or new_row >= list_widget.count():
            return
        item = list_widget.takeItem(row)
        list_widget.insertItem(new_row, item)
        list_widget.setCurrentRow(new_row)
        uid = item.data(Qt.ItemDataRole.UserRole)
        if list_widget == self.embed_list:
            if 0 <= row < len(self.embed_pipeline) and 0 <= new_row < len(self.embed_pipeline):
                self.embed_pipeline[row], self.embed_pipeline[new_row] = (
                    self.embed_pipeline[new_row],
                    self.embed_pipeline[row],
                )
            self._sync_extract_move(uid, direction)
            self._update_step_labels(self.embed_list)
        else:
            if 0 <= row < len(self.extract_pipeline) and 0 <= new_row < len(self.extract_pipeline):
                self.extract_pipeline[row], self.extract_pipeline[new_row] = (
                    self.extract_pipeline[new_row],
                    self.extract_pipeline[row],
                )
            self._update_step_labels(self.extract_list)

    def _sync_extract_move(self, target_id, direction):
        """Move item in extract list to match embed list reorder."""
        idx = -1
        for i in range(self.extract_list.count()):
            if self.extract_list.item(i).data(Qt.ItemDataRole.UserRole) == target_id:
                idx = i
                break
        if idx < 0:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= self.extract_list.count():
            return
        item = self.extract_list.takeItem(idx)
        self.extract_list.insertItem(new_idx, item)
        self.extract_list.setCurrentRow(new_idx)
        if 0 <= idx < len(self.extract_pipeline) and 0 <= new_idx < len(self.extract_pipeline):
            self.extract_pipeline[idx], self.extract_pipeline[new_idx] = (
                self.extract_pipeline[new_idx],
                self.extract_pipeline[idx],
            )
        self._update_step_labels(self.extract_list)

    def commit_stego_config(self):
        """Append current technique as one step to both embed and extract pipelines."""
        tech = self.tech_combo.currentText()
        encrypted = self.encryption_box.isChecked()
        name = tech.split("(")[0].strip()
        display = f"{name}" + (" (Encrypted)" if encrypted else "")
        step_id = str(uuid.uuid4())
        self._add_list_item(self.embed_list, display, step_id)
        self._add_list_item(self.extract_list, display, step_id)
        cfg = {"id": step_id, "technique": tech, "encrypted": encrypted, "display": display}
        self.embed_pipeline.append(cfg)
        self.extract_pipeline.append(cfg)
        self._update_step_labels(self.embed_list)
        self._update_step_labels(self.extract_list)

    def _remove_from_embed_pipeline(self):
        """Remove selected item from both pipelines by id."""
        row = self.embed_list.currentRow()
        if row < 0:
            return
        item = self.embed_list.item(row)
        uid = item.data(Qt.ItemDataRole.UserRole)
        if not uid:
            return
        self.embed_list.takeItem(row)
        self.embed_pipeline = [p for p in self.embed_pipeline if p.get("id") != uid]
        for i in range(self.extract_list.count()):
            if self.extract_list.item(i).data(Qt.ItemDataRole.UserRole) == uid:
                self.extract_list.takeItem(i)
                break
        self.extract_pipeline = [p for p in self.extract_pipeline if p.get("id") != uid]
        self._update_step_labels(self.embed_list)
        self._update_step_labels(self.extract_list)

    def _remove_from_extract_pipeline(self):
        """Remove selected item from extract list and pipeline."""
        row = self.extract_list.currentRow()
        if row < 0:
            return
        item = self.extract_list.item(row)
        uid = item.data(Qt.ItemDataRole.UserRole)
        if not uid:
            return
        self.extract_list.takeItem(row)
        self.extract_pipeline = [p for p in self.extract_pipeline if p.get("id") != uid]
        self._update_step_labels(self.extract_list)

    def _clear_all_pipelines(self):
        """Clear both list widgets and pipeline data."""
        self.embed_list.clear()
        self.extract_list.clear()
        self.embed_pipeline = []
        self.extract_pipeline = []

    def _clear_extract_pipeline(self):
        """Clear extract list and pipeline only."""
        self.extract_list.clear()
        self.extract_pipeline = []

    def _export_pipeline_config(self):
        """Save embed and extract pipeline to a JSON file for Extract page or future Import as template."""
        data = {
            "version": 1,
            "embed_pipeline": getattr(self, "embed_pipeline", []),
            "extract_pipeline": getattr(self, "extract_pipeline", []),
        }
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Pipeline Config",
            "",
            "JSON (*.json);;All Files (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            QMessageBox.information(
                self,
                "Export Config",
                f"Pipeline configuration saved to:\n{path}",
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to save config:\n{e}",
            )

    def create_preview_area(self):
        stack = QStackedWidget()
        stack.addWidget(self.create_lsb_page())
        stack.addWidget(self.create_locomotive_page())
        stack.addWidget(self.create_metadata_editor_page())
        return stack
    
    def create_locomotive_list_widget(self):
        widget = QListWidget()
        widget.setViewMode(QListWidget.ViewMode.IconMode)
        widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        widget.setMovement(QListWidget.Movement.Static)
        widget.setFlow(QListWidget.Flow.LeftToRight)
        widget.setWrapping(True)
        widget.setSpacing(12)
        widget.setGridSize(QSize(130, 160))
        widget.setStyleSheet(LOCO_LIST_STYLE)
        return widget
    
    def create_locomotive_button_row(self):
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        
        btn_add = QPushButton("+ Add Files")
        btn_add.clicked.connect(self.browse_locomotive_files_append)
        
        btn_del = QPushButton("Delete Selected")
        # btn_del.clicked.connect(self.delete_selected_locomotive_files)
        
        btn_clear = QPushButton("Clear All")
        # btn_clear.clicked.connect(self.clear_locomotive_files)
        
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        return btn_row
    
    def build_locomotive_list_section(self, mode):
        title = f"Selected Files ({len(self.locomotive_files)} fragments)"
        
        loco_group_box = QGroupBox(title)
        self.loco_group_box = loco_group_box
        
        loco_group_box.setMinimumHeight(200)
            
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 12, 6, 6)
        layout.setSpacing(6)

        loco_list_widget = self.create_locomotive_list_widget()
        loco_list_widget.setMinimumHeight(150)
        
        self.loco_list_widget = loco_list_widget
            
        layout.addWidget(loco_list_widget, 1)
        
        # Add control buttons for both standalone and configurable modes
        btn_row = self.create_locomotive_button_row()
        layout.addLayout(btn_row, 0)
        
        loco_group_box.setLayout(layout)
        return loco_group_box

    # Components(Groupbox) of right panel
    def create_lsb_page(self):
        page = QWidget()
        page.setMinimumSize(400, 400)
        
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        
        # Wrap content stack in scroll area to prevent overflow
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)
        
        self.standalone_content_stack = QStackedWidget()
        self.standalone_content_stack.addWidget(self.build_preview_section_with_stats())
        
        content_layout.addWidget(self.standalone_content_stack, 1)
        scroll_area.setWidget(content_widget)
        
        layout.addWidget(scroll_area, 1)
        layout.addWidget(self.build_execution_group("Embed Data", "std"), 0)
        return page
    
    def create_locomotive_page(self):
        page = QWidget()
        page.setMinimumSize(400, 400)
        
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        
        # Scroll area for locomotive list to prevent overflow
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        
        self.loco_list_box = self.build_locomotive_list_section("std")
        scroll_area.setWidget(self.loco_list_box)
        
        layout.addWidget(scroll_area, 1)
        layout.addWidget(self.build_execution_group("Execute Locomotive Embedding", "loco"), 0)
        return page
    
    def create_metadata_editor_page(self):
        self.metadata_editor = MetadataEditorWidget()
        
        box = QGroupBox("Metadata Editor")
        layout = QVBoxLayout(box)       
        layout.addWidget(self.metadata_editor)
        
        return box
    
    def build_preview_section_with_stats(self):
        """Preview section with stats display (for LSB++ mode)"""
        group_box = QGroupBox("Preview")
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(6, 12, 6, 6)
        group_layout.setSpacing(6)
        
        # Preview Label with drag-and-drop support
        self.preview_label = DraggablePreviewLabel(allowed_extensions=['.png'])
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setText("No Image Selected\n\nSelect PNG image  from left panel\nor drag & drop PNG file here")
        self.preview_label.setStyleSheet("""
            QLabel {
                border: 2px dashed #555;
                background-color: #222;
                color: #888;
                font-size: 10pt;
            }
        """)
        self.preview_label.setMinimumHeight(200)
        self.preview_label.setScaledContents(False)
        
        
        self.preview_label.file_dropped.connect(self.on_lsb_preview_image_dropped)
        
        group_layout.addWidget(self.preview_label, 1)
        
        # Info Label (file info)
        preview_info_label = QLabel("")
        preview_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_info_label.setStyleSheet("color: #e0e0e0; font-size: 9pt;")
        preview_info_label.hide()
        setattr(self, f"preview_info_label", preview_info_label)
        
        group_layout.addWidget(preview_info_label, 0)
        
        # Stats Row (below preview)
        stats_container = self.build_stats_row()
        group_layout.addWidget(stats_container, 0)
        
        group_box.setLayout(group_layout)
        return group_box
    
    def build_stats_row(self):
        """Build stats display row"""
        container = QWidget()
        container.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px;
            }
        """)
        
        layout = QHBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)
        
        
        # File Name Stat
        self.stat_filename = self.create_stat_item("File:", "No Image", "#e0e0e0")
        layout.addWidget(self.stat_filename)
        
        # Image Size Stat
        self.stat_image_size = self.create_stat_item("Image Size:", "No Image", "#e0e0e0")
        layout.addWidget(self.stat_image_size)
        
        # Max Capacity Stat
        self.stat_capacity = self.create_stat_item("Max Capacity:", "0 KB", "#e0e0e0")
        layout.addWidget(self.stat_capacity)       
        
        return container
    
    def update_lsb_preview_stats(self, image_path=None, payload_size=0):
        # 1. ใช้การอ้างอิงตรงๆ หรือเช็คผ่าน hasattr (ถ้าไม่ชัวร์ว่าสร้าง Widget หรือยัง)
        if not hasattr(self, 'stat_image_size'): return
        
        # 2. เตรียม Widgets ไว้ใช้งาน
        lbl_name = self.stat_filename.value_label
        lbl_img = self.stat_image_size.value_label
        lbl_cap = self.stat_capacity.value_label

        if image_path and os.path.exists(image_path):
            try:
                with Image.open(image_path) as img:
                    width, height = img.size
                    file_size = os.path.getsize(image_path)
                    filename = os.path.basename(image_path)
                    if len(filename) > 20:
                        display_name = filename[:10] + "..." + filename[-7:]
                    else:
                        display_name = filename
                    
                    lbl_name.setText(display_name)
                    lbl_name.setToolTip(image_path)
                    
                    # แสดงขนาดภาพและขนาดไฟล์
                    lbl_img.setText(f"{width}×{height} ({format_file_size(file_size)})")
                    
                    lbl_cap.setText("Calculating...")
                    self.max_capacity_bytes = 0
                    

            except Exception as e:
                print(f"Error updating stats: {e}")
        else:
            # Reset ทุกอย่างให้เป็นค่าเริ่มต้น (ถ้าไม่มีภาพ)
            lbl_img.setText("No Image")
            lbl_cap.setText("0 B")
            self.max_capacity_bytes = 0
            lbl_name.setText("None")
            lbl_name.setToolTip("")
            
    def update_meta_preview_stats(self, file_path=None):

        lbl_name = self.meta_stat_filename.value_label
        lbl_size = self.meta_stat_image_size.value_label

        if file_path and os.path.exists(file_path):
            try:
                with Image.open(file_path) as img:
                    width, height = img.size
                    file_size = os.path.getsize(file_path)
                    filename = os.path.basename(file_path)
                    if len(filename) > 20:
                        display_name = filename[:10] + "..." + filename[-7:]
                    else:
                        display_name = filename
                    
                    lbl_name.setText(display_name)
                    lbl_name.setToolTip(file_path)
                    
                    # แสดงขนาดภาพและขนาดไฟล์
                    lbl_size.setText(f"{width}×{height} ({format_file_size(file_size)})")
                    
                    

            except Exception as e:
                print(f"Error updating stats: {e}")
        else:
            # Reset ทุกอย่างให้เป็นค่าเริ่มต้น (ถ้าไม่มีภาพ)
            lbl_name.setText("None")
            lbl_name.setToolTip("")
            lbl_size.setText("0 B")
            
    def build_execution_group(self, button_text, prefix):
        """
        สร้าง Execution Group สำหรับ LSB++ (std) และ Locomotive (loco)
        โดยจะซ่อนตัวเองอัตโนมัติเมื่ออยู่ใน Configurable Mode
        """
        container = QWidget()
        container.setMinimumHeight(60)
        container.setMaximumHeight(80)
        
        # ⭐ ตั้งค่า Size Policy ให้ยุบได้เมื่อซ่อน
        size_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        size_policy.setRetainSizeWhenHidden(False)  # 🔑 สำคัญมาก: ไม่เว้นพื้นที่เมื่อซ่อน
        container.setSizePolicy(size_policy)
        
        # เก็บ container เพื่อให้สามารถซ่อน/แสดงได้ในภายหลัง
        setattr(self, f"{prefix}_execution_container", container)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        
        # สร้างปุ่มและตั้งชื่อตัวแปรแบบ Dynamic ตาม prefix
        btn_exec = QPushButton(button_text)
        btn_exec.setMinimumHeight(35)
        btn_exec.setStyleSheet(
            "font-weight: bold; font-size: 11pt; "
            "background-color: #2d5a75; border-radius: 4px; color: white;"
        )
        setattr(self, f"{prefix}_btn_exec", btn_exec)
        
        btn_savestg = QPushButton("Save stego")
        btn_savestg.setMinimumHeight(35)
        btn_savestg.setStyleSheet(
            "font-weight: bold; font-size: 11pt; "
            "background-color: #888; border-radius: 4px; color: white;"
        )
        btn_savestg.setEnabled(False)
        btn_savestg.hide()
        setattr(self, f"{prefix}_btn_savestg", btn_savestg)
        
        # Progress Bar
        progress_bar = QProgressBar()
        progress_bar.setValue(0)
        progress_bar.setTextVisible(False)
        progress_bar.setFixedHeight(6)
        setattr(self, f"{prefix}_progress_bar", progress_bar)
        
        # Status Label
        status_label = QLabel("Ready.")
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_label.setStyleSheet("color: #888; font-size: 9pt;")
        setattr(self, f"{prefix}_status_label", status_label)
        
        # Connect Signal
        btn_exec.clicked.connect(lambda: self.on_run_embed())
        
        # Layout
        hlayout = QHBoxLayout() 
        hlayout.setSpacing(10)
        hlayout.addWidget(btn_exec)
        hlayout.addWidget(btn_savestg)

        layout.addLayout(hlayout)
        layout.addWidget(progress_bar)
        layout.addWidget(status_label)
        
        # ตรวจสอบว่าอยู่ใน Configurable Mode หรือไม่ เพื่อซ่อน container
        is_config = hasattr(self, 'mode_combo') and self.mode_combo.currentText() == "Configurable Model"
        if is_config:
            container.setVisible(False)
        
        return container
    
    def on_save_stego(self, stego_data, metrics):
        """
        ฟังก์ชันบันทึกผลลัพธ์ (รองรับทั้ง LSB++ และ Locomotive)
        """
        ui = self.get_active_ui()
        
        try:
            # =========================================================
            # CASE A: Locomotive (ข้อมูลที่ส่งมาเป็น String Path)
            # =========================================================
            if isinstance(stego_data, str):
                src_path = stego_data
                
                # กรณี 1: เป็นไฟล์เดียว (Fragmentation Mode)
                if os.path.isfile(src_path):
                    default_name = os.path.basename(src_path)
                    save_path, _ = QFileDialog.getSaveFileName(
                        self, "Save Stego File", default_name, "PNG Images (*.png)"
                    )
                    
                    if save_path:
                        shutil.copy2(src_path, save_path) # ใช้ shutil ก๊อปปี้ไฟล์
                        
                        QMessageBox.information(self, "Success", f"File saved to:\n{save_path}")
                        if ui['status']: ui['status'].setText("Saved successfully.")
                        # Update Configurable Editor status and record step to pipeline
                        is_config = hasattr(self, 'mode_combo') and self.mode_combo.currentText() == "Configurable Model"
                        if is_config:
                            self.commit_stego_config()
                            if hasattr(self, 'cfg_embed_status_label'):
                                self.cfg_embed_status_label.setText("Saved successfully.")
                            if hasattr(self, 'cfg_extract_status_label'):
                                self.cfg_extract_status_label.setText("Saved successfully.")
                    else:
                        if ui['status']: ui['status'].setText("Save cancelled.")
                        # Update Configurable Editor status (both tabs)
                        is_config = hasattr(self, 'mode_combo') and self.mode_combo.currentText() == "Configurable Model"
                        if is_config:
                            if hasattr(self, 'cfg_embed_status_label'):
                                self.cfg_embed_status_label.setText("Save cancelled.")
                            if hasattr(self, 'cfg_extract_status_label'):
                                self.cfg_extract_status_label.setText("Save cancelled.")
                        
                # กรณี 2: เป็นโฟลเดอร์ (Sharding Mode - หลายรูป)
                elif os.path.isdir(src_path):
                    save_dir = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
                    
                    if save_dir:
                        dir_name = os.path.basename(src_path)
                        target_path = os.path.join(save_dir, dir_name)
                        
                        # ถ้ามีโฟลเดอร์ชื่อซ้ำ ให้ลบของเก่าก่อน
                        if os.path.exists(target_path):
                            shutil.rmtree(target_path)
                             
                        shutil.copytree(src_path, target_path) # ก๊อปปี้ทั้งโฟลเดอร์
                        
                        QMessageBox.information(self, "Success", f"Output folder saved to:\n{target_path}")
                        if ui['status']: ui['status'].setText("Saved successfully.")
                        is_config = hasattr(self, 'mode_combo') and self.mode_combo.currentText() == "Configurable Model"
                        if is_config:
                            self.commit_stego_config()
                            if hasattr(self, 'cfg_embed_status_label'):
                                self.cfg_embed_status_label.setText("Saved successfully.")
                            if hasattr(self, 'cfg_extract_status_label'):
                                self.cfg_extract_status_label.setText("Saved successfully.")
                    else:
                        if ui['status']: ui['status'].setText("Save cancelled.")

            # =========================================================
            # CASE B: LSB++ (ข้อมูลที่ส่งมาเป็น Numpy Array รูปภาพ)
            # =========================================================
            else:
                # ตั้งชื่อไฟล์ Default
                if self.current_file_path:
                    orig_name = os.path.splitext(os.path.basename(self.current_file_path))[0]
                    default_save_name = f"{orig_name}_stego.png"
                else:
                    default_save_name = "stego_image.png"
                
                save_path, _ = QFileDialog.getSaveFileName(
                    self, 
                    "Save Stego Image", 
                    default_save_name, 
                    "PNG Images (*.png)"
                )

                if save_path:
                    if Image: 
                        # แปลง Array กลับเป็นรูปแล้วบันทึก
                        final_image = Image.fromarray(stego_data)
                        final_image.save(save_path)

                        # สร้างข้อความแสดงผล Metrics (ถ้ามี)
                        info_msg = "Embedding Completed Successfully!\n\n"
                        if metrics:
                            info_msg += (
                                f"--- Quality Metrics ---\n"
                                f"PSNR: {metrics.psnr:.2f} dB\n"
                                f"SSIM: {metrics.ssim:.4f}\n"
                                f"Drift: {metrics.hist_drift:.4f}\n"
                            )
                        info_msg += f"Saved to: {save_path}"
                        
                        QMessageBox.information(self, "Success", info_msg)
                        if ui['status']:
                            ui['status'].setText("Saved successfully.")
                        is_config = hasattr(self, 'mode_combo') and self.mode_combo.currentText() == "Configurable Model"
                        if is_config:
                            self.commit_stego_config()
                            if hasattr(self, 'cfg_embed_status_label'):
                                self.cfg_embed_status_label.setText("Saved successfully.")
                            if hasattr(self, 'cfg_extract_status_label'):
                                self.cfg_extract_status_label.setText("Saved successfully.")
                    else:
                        QMessageBox.critical(self, "Error", "PIL library missing.")
                else:
                    if ui['status']:
                        ui['status'].setText("Save cancelled.")

        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Error during saving:\n{str(e)}")
    
    def on_lsb_preview_image_dropped(self, file_path):
        """Handle image dropped on preview area"""
        try:
            # Validate file exists
            if not os.path.exists(file_path):
                QMessageBox.warning(self, "Error", "File not found!")
                return
            
            # Validate PNG file
            if not file_path.lower().endswith('.png'):
                QMessageBox.warning(self, "Error", "Only PNG files are supported!")
                return
            
            # Same logic as browse_single_image()
            self.current_file_path = file_path
            self.carrier_edit.setText(file_path)
            self.load_image_preview(file_path)
            
            # อัปเดต Stats เบื้องต้น
            payload_size = self.update_payload_size()
            self.update_lsb_preview_stats(file_path, payload_size)
            self.update_capacity_indicator()
            
            # เริ่มคำนวณความจุละเอียด (Worker จะมาอัปเดต UI อีกทีเมื่อเสร็จ)
            self.start_capacity_calculation(file_path)
            
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image:\n{str(e)}")
                    
    def on_meta_preview_file_dropped(self, file_path):
        """Handle image dropped on preview area"""
        try:
            # Validate file exists
            if not os.path.exists(file_path):
                QMessageBox.warning(self, "Error", "File not found!")
                return
            
            # Validate PNG file
            valid_extensions = ('.png', '.jpg', '.jpeg', '.mp3')

            if not file_path.lower().endswith(valid_extensions):
                QMessageBox.warning(self, "Error", "Only (JPEG, PNG, MP3) files are supported!")
                return
            
            self.current_file_path = file_path
            self.carrier_edit.setText(file_path)
            self.update_meta_preview_stats(file_path)
            self.load_file_preview(file_path)
            
            self.metadata_editor.load_file(file_path)
            
            
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image:\n{str(e)}")
            
    def create_stat_item(self, label_text, value_text, color):
        """Create a single stat item"""
        widget = QWidget()
        widget.setStyleSheet("background: transparent; border: none;")
        
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Label
        label = QLabel(label_text)
        label.setStyleSheet("color: #888; font-size: 9pt; background: transparent; border: none;")
        
        # Value
        value = QLabel(value_text)
        value.setObjectName(f"stat_value_{label_text.replace(':', '').replace(' ', '_').lower()}")
        value.setStyleSheet(f"color: {color}; font-size: 9pt; background: transparent; border: none;")
        
        layout.addWidget(label)
        layout.addWidget(value)
        layout.addStretch()
        
        # Store reference to value label
        widget.value_label = value
        
        return widget
    
    def get_active_ui(self):
        """Helper เพื่อดึง widget ควบคุมของหน้าที่ active อยู่"""
        if self.preview_stack.currentIndex() == PAGE_LOCOMOTIVE:
            return {
                'btn_exec': getattr(self, 'loco_btn_exec', None),
                'btn_save': getattr(self, 'loco_btn_savestg', None),
                'progress': getattr(self, 'loco_progress_bar', None),
                'status': getattr(self, 'loco_status_label', None)
            }
        else:
            # Default to Standalone (std)
            return {
                'btn_exec': getattr(self, 'std_btn_exec', None),
                'btn_save': getattr(self, 'std_btn_savestg', None),
                'progress': getattr(self, 'std_progress_bar', None),
                'status': getattr(self, 'std_status_label', None)
            }
            
    