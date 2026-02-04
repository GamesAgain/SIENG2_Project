# PYQT6 FRAMEWORK (GUI)
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

try:
    from PIL import Image
except ImportError:
    Image = None
    
    
from app.core.stego.lsb_plus.engine.embedding import calculate_exact_capacity
from app.core.stego.lsb_plus.lsbpp import LSBPP
from app.utils.file_io import format_file_size
from app.utils.gui_helpers import disconnect_signal_safely

import numpy as np
from app.core.stego.lsb_plus.engine.analyzer.capacity import compute_capacity
from app.core.stego.lsb_plus.engine.analyzer.texture_map import compute_texture_features


# ============================================================================
# CONSTANTS & STYLES
# ============================================================================

PAGE_STANDALONE = 0
PAGE_LOCOMOTIVE = 1
PAGE_CONFIGURABLE = 2

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
            
            # --- DEBUG LOG ---
            # ดูค่านี้ใน Terminal ว่าได้เท่าไหร่? (ควรจะได้ประมาณ 644 bits สำหรับภาพ 2004.png)
            print(f"[DEBUG] Total Bits Found: {total_bits}") 
            # -----------------

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

    finished_signal = pyqtSignal(object, object)
    error_signal = pyqtSignal(str)
    
    progress_signal = pyqtSignal(str, int) 

    def __init__(self, engine, cover_path, payload_data, mode_str, pwd, pub_key):
        super().__init__()
        self.engine = engine
        self.cover_path = cover_path
        self.payload_data = payload_data
        self.mode_str = mode_str
        self.pwd = pwd
        self.pub_key = pub_key

    def run(self):
        """Background Thread"""
        try:
            def worker_callback(text, percent):
                self.progress_signal.emit(text, percent)

            stego_rgb, metrics = self.engine.embed(
                cover_path=self.cover_path,
                payload_text=self.payload_data,
                encrypt_mode=self.mode_str,
                password=self.pwd,
                public_key_path=self.pub_key,
                status_callback=worker_callback
            )
            
            self.finished_signal.emit(stego_rgb, metrics)
            
        except Exception as e:
            self.error_signal.emit(str(e))
            
# ============================================================================
# CUSTOM WIDGETS
# ============================================================================

class DraggablePreviewLabel(QLabel):
    """QLabel with drag-and-drop support for PNG images"""
    image_dropped = pyqtSignal(str)  # Emit file path when image dropped
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._original_style = ""
    
    def dragEnterEvent(self, event):
        """Handle drag enter - check if it's a PNG file"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1:
                file_path = urls[0].toLocalFile()
                if file_path.lower().endswith('.png'):
                    event.acceptProposedAction()
                    # Visual feedback: change border color to blue
                    self._original_style = self.styleSheet()
                    new_style = self._original_style.replace('border: 2px dashed #555', 'border: 2px dashed #3daee9')
                    self.setStyleSheet(new_style)
                    return
        event.ignore()
    
    def dragLeaveEvent(self, event):
        """Restore original style when drag leaves"""
        if self._original_style:
            self.setStyleSheet(self._original_style)
    
    def dropEvent(self, event):
        """Handle file drop"""
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith('.png'):
                self.image_dropped.emit(file_path)
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
       
       self.original_preview_pixmaps = {}  # Store original pixmaps for scaling
       self._init_ui()
       
    def _init_ui(self):
        self.setMinimumSize(800, 500)
        
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)
        
        left_panel = self._create_left_panel()
        self.right_panel_stack = self._create_right_panel()
        
        #ratio: left panel gets 35%, right panel gets 65%
        main_layout.addWidget(left_panel, 35)
        main_layout.addWidget(self.right_panel_stack, 65)
        
        self.on_technique_changed()
                
    def on_technique_changed(self):
        current_tech = self.tech_combo.currentText()
        is_LSBPP = "LSB++" in current_tech
        is_locomotive = "Locomotive" in current_tech
        is_metadata = "Metadata" in current_tech
        
        disconnect_signal_safely(self.carrier_browse_btn.clicked)
        
        if is_LSBPP:
            self.carrier_browse_btn.clicked.connect(self.browse_single_image)     
            

    def _on_run_embed(self):
        """
        Main execution handler:
        1. Validates inputs.
        2. Prepares data (UI -> Variables).
        3. Starts the Background Worker Thread.
        """
        
        if not hasattr(self, 'current_image_path') or not self.current_image_path:
            QMessageBox.warning(self, "Missing Input", "Please select a carrier image first!")
            return

        current_tab_index = self.payload_tabs.currentIndex()
        payload_data = None
        
        if current_tab_index == TAB_INDEX_TEXT:
            # Text Mode
            text_content = self.payload_text.toPlainText()
            if not text_content:
                QMessageBox.warning(self, "Missing Input", "Please enter a message to embed!")
                return
            payload_data = text_content # ส่งเป็น String
            
        elif current_tab_index == TAB_INDEX_FILE:
            # File Mode
            file_path = self.payload_file_path.text()
            if not file_path or not os.path.exists(file_path):
                QMessageBox.warning(self, "Missing Input", "Please select a valid payload file!")
                return
            
            try:
                # หมายเหตุ: ถ้า LSBPP รองรับ bytes ให้ใช้ 'rb' 
                # แต่ถ้ายังเป็น version รับ string ให้ใช้ 'r' (utf-8)
                with open(file_path, 'r', encoding='utf-8') as f:
                    payload_data = f.read()
            except Exception as e:
                QMessageBox.critical(self, "File Error", f"Could not read payload file:\n{str(e)}")
                return
            
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

        self.btn_exec.setEnabled(False)
        self.btn_savestg.setEnabled(False); self.btn_savestg.hide()
        self.standalone_status_label.setText("Initializing...")
        self.standalone_progress_bar.setRange(0, 100)
        self.standalone_progress_bar.setValue(0)

        try:
            engine = LSBPP()

            # สร้าง Worker (ส่งข้อมูลที่เตรียมไว้เข้าไป)
            self.worker = EmbedWorker(
                engine, 
                self.current_image_path, 
                payload_data, 
                mode_str, 
                pwd, 
                pub_key_path
            )
            
            # เชื่อมต่อ Signals (สั่งงานข้าม Thread)
            self.worker.progress_signal.connect(self._update_progress_ui) # อัปเดตหลอดโหลด
            self.worker.finished_signal.connect(self._on_embed_finished)  # ทำเสร็จแล้วไปหน้า Save
            self.worker.error_signal.connect(self._on_embed_error)        # ถ้าพังให้แจ้งเตือน
            
            # ลบ Thread ทิ้งเมื่อจบงานเพื่อคืน Ram
            self.worker.finished.connect(self.worker.deleteLater)

            self.worker.start()

        except Exception as e:
            # กรณีพังตั้งแต่ตอนสร้าง Worker (ยังไม่ได้รัน)
            self._on_embed_error(str(e))
            
    # ฟังก์ชันรับค่า Update จาก Worker มาแสดงผลบนจอ
    def _update_progress_ui(self, text, percent):
        """ทำงานบน Main Thread: อัปเดตข้อความและ Progress Bar"""
        self.standalone_status_label.setText(text)
        self.standalone_progress_bar.setValue(percent)

    # ฟังก์ชันจบงาน (Success Handling)
    def _on_embed_finished(self, stego_rgb, metrics):
        """ทำงานเมื่อ Worker ประมวลผลเสร็จสิ้น"""
        
        self.standalone_progress_bar.setValue(100)
        self.standalone_status_label.setText("Processing Complete.")
        self.btn_exec.setEnabled(True)
        self.btn_savestg.setEnabled(True)
        
        self.btn_savestg.show()
        self.btn_savestg.setEnabled(True)
        
        try:
            self.btn_savestg.clicked.disconnect()
        except TypeError:
            pass
        
        self.btn_savestg.clicked.connect(
            lambda: self._on_save_stego(stego_rgb, metrics)
        )
        

    # ฟังก์ชันจัดการ Error
    def _on_embed_error(self, error_msg):
        """ทำงานเมื่อ Worker ส่ง Error กลับมา"""
        self.standalone_status_label.setText("Error occurred.")
        self.standalone_progress_bar.setValue(0)
        self.btn_exec.setEnabled(True)
        
        QMessageBox.critical(self, "Embedding Error", error_msg)

        
    def browse_single_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Carrier Image", "", "PNG Images (*.png)"
        )
        if file_path:
            self.current_image_path = file_path
            self.carrier_edit.setText(file_path)
            self._load_image_preview(file_path)    
            payload_size = self._update_payload_size()
            self._update_stats(file_path, payload_size)
            self.update_capacity_indicator()
            
            self._start_capacity_calculation(file_path)
            
    def _update_payload_size(self):
        return len(self.payload_text.toPlainText().encode()) if hasattr(self, 'payload_text') else 0
            
    def _load_image_preview(self, image_path):
        pixmap = QPixmap(image_path)
        self.original_preview_pixmaps = pixmap
        
        if not pixmap.isNull():
            self._update_preview_scaling()
            
    def _update_preview_scaling(self):
        """Update all preview labels with proper scaling based on current size."""
        # 1. เช็คก่อนว่ามีรูปภาพให้ประมวลผลไหม (กัน Crash)
        pixmap = getattr(self, 'original_preview_pixmaps', None)
        if pixmap is None or pixmap.isNull():
            return

        # 2. คำนวณขนาด
        label_width = self.preview_label.width()
        if label_width <= 0:
            label_width = 500
            
        max_height = min(500, int(self.height() * 0.5))
        if max_height < 250:
            max_height = 250
        
        # 3. ประมวลผลภาพ
        scaled_pixmap = pixmap.scaled(
            label_width, max_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        # 4. อัปเดต UI 
        self.preview_label.setPixmap(scaled_pixmap)
        
        
            
    def _create_left_panel(self):
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
        
        layout.addWidget(self._build_mode_section())
        layout.addWidget(self._build_technique_section())
        layout.addWidget(self._build_carrier_section())
        layout.addWidget(self._build_payload_section(), 1)
        layout.addWidget(self._build_encryption_section())
        layout.addStretch()
        
        scroll_area.setWidget(widget)
        return scroll_area
    
    # Components(Groupbox) of left panel
    def _build_mode_section(self):
        return self._create_combo_group("Mode Selection", [
            (
                "Standalone", 
                "Hide data using one specific method independently."
            ),
            (
                "Configurable Model", 
                "Create a custom process by combining multiple techniques."
            )
        ], "mode_combo")

    def _build_technique_section(self):
        return self._create_combo_group("Technique Selection", [
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
    
    def _create_combo_group(self, title, items, attribute_name):
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
        combo.currentIndexChanged.connect(self.on_technique_changed)
        
        layout.addWidget(combo)
        box.setLayout(layout)
        return box
        
    def _build_carrier_section(self):
            box = QGroupBox("Carrier Input")
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
    
    def _build_payload_section(self):
        box = QGroupBox("Payload Input")
        self.payload_main_group = box
        box.setMinimumHeight(200)
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 12, 6, 6)
        layout.setSpacing(4)
        
        self.payload_stack = QStackedWidget()
        self.payload_stack.addWidget(self._create_standard_payload_page())
        # self.payload_stack.addWidget(self._create_metadata_payload_page())
        
        size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        size_policy.setVerticalStretch(1)
        self.payload_stack.setSizePolicy(size_policy)
        
        layout.addWidget(self.payload_stack, 1)
        box.setLayout(layout)
        return box
    
    def _create_standard_payload_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.payload_tabs = QTabWidget()
        self.payload_tabs.addTab(self._create_text_payload_tab(), "Text Message")
        self.payload_tabs.addTab(self._create_file_payload_tab(), "File Attachment")
        
        layout.addWidget(self.payload_tabs)
        return page
    
    def _create_text_payload_tab(self):
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
    
    def _create_file_payload_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 10, 5, 10)  # Balanced top/bottom spacing
        layout.setSpacing(6)
        
        self.payload_file_path = QLineEdit()
        self.payload_file_path.setPlaceholderText("Path to secret file...")
        self.payload_file_path.hide()
        
        self.attachment_widget = AttachmentDropWidget()
        self.attachment_widget.fileSelected.connect(self._on_file_selected)
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
            self._update_payload_size()
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
        self._update_payload_size()
            
    def _start_capacity_calculation(self, image_path):
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
    
    def _on_file_selected(self, file_path):
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

    def _on_public_key_selected(self, file_path):
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
                        
    def _build_encryption_section(self):
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
        
        self.enc_combo.currentIndexChanged.connect(self._toggle_encryption_inputs)
        type_row.addWidget(self.lbl_key)
        type_row.addWidget(self.enc_combo)
        layout.addLayout(type_row)

        self.enc_stack = QStackedWidget()
        self.enc_stack.addWidget(self._create_password_page())
        self.enc_stack.addWidget(self._create_public_key_page())
        
        layout.addWidget(self.enc_stack)
        self.encryption_box.setLayout(layout)
        
        self.encryption_box.toggled.connect(self.enc_combo.setEnabled)
        self.encryption_box.toggled.connect(self.enc_stack.setEnabled)
        
        return self.encryption_box
    
    def _toggle_encryption_inputs(self):
        self.enc_stack.setCurrentIndex(self.enc_combo.currentIndex())
        
    def _create_password_page(self):
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_pass = QLabel("Password:")
        self.passphrase = QLineEdit()
        self.passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.passphrase.setPlaceholderText("Enter Passphrase...")
        self._add_visibility_toggle(self.passphrase)
        
        self.lbl_confirm = QLabel("Confirm:")
        self.confirmpassphrase = QLineEdit()
        self.confirmpassphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirmpassphrase.setPlaceholderText("Confirm Passphrase...")
        self._add_visibility_toggle(self.confirmpassphrase)

        layout.addWidget(self.lbl_pass, 0, 0)
        layout.addWidget(self.passphrase, 0, 1)
        layout.addWidget(self.lbl_confirm, 1, 0)
        layout.addWidget(self.confirmpassphrase, 1, 1)
        
        return page
    
    def _add_visibility_toggle(self, line_edit):
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
    
    def _create_public_key_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)  # เปลี่ยนเป็น QVBoxLayout เพื่อจัดวางง่ายขึ้น
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

        # เชื่อม Signal
        self.pubkey_attachment.requestBrowse.connect(self.browse_public_key)
        self.pubkey_attachment.fileSelected.connect(self._on_public_key_selected)

        layout.addWidget(self.pubkey_attachment)

        return page
        
    def _create_right_panel(self):
        stack = QStackedWidget()
        stack.addWidget(self._create_standalone_page())
        # stack.addWidget(self._create_locomotive_page())
        # stack.addWidget(self._create_configurable_page())
        return stack
    
    # Components(Groupbox) of right panel
    def _create_standalone_page(self):
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
        self.standalone_content_stack.addWidget(self._build_preview_section_with_stats())
        # self.standalone_content_stack.addWidget(self._create_metadata_editor_container("std"))
        
        content_layout.addWidget(self.standalone_content_stack, 1)
        scroll_area.setWidget(content_widget)
        
        layout.addWidget(scroll_area, 1)
        layout.addWidget(self._build_execution_group("Embed Data"), 0)
        return page
    
    def _build_preview_section_with_stats(self):
        """Preview section with stats display (for LSB++ mode)"""
        group_box = QGroupBox("Preview")
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(6, 12, 6, 6)
        group_layout.setSpacing(6)
        
        # Preview Label with drag-and-drop support
        self.preview_label = DraggablePreviewLabel()
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
        
        
        self.preview_label.image_dropped.connect(self._on_preview_image_dropped)
        
        group_layout.addWidget(self.preview_label, 1)
        
        # Info Label (file info)
        preview_info_label = QLabel("")
        preview_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_info_label.setStyleSheet("color: #e0e0e0; font-size: 9pt;")
        preview_info_label.hide()
        setattr(self, f"preview_info_label", preview_info_label)
        
        group_layout.addWidget(preview_info_label, 0)
        
        # Stats Row (below preview)
        stats_container = self._build_stats_row()
        group_layout.addWidget(stats_container, 0)
        
        group_box.setLayout(group_layout)
        return group_box
    
    def _build_stats_row(self):
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
        self.stat_filename = self._create_stat_item("File:", "No Image", "#e0e0e0")
        layout.addWidget(self.stat_filename)
        
        # Image Size Stat
        self.stat_image_size = self._create_stat_item("Image Size:", "No Image", "#e0e0e0")
        layout.addWidget(self.stat_image_size)
        
        # Max Capacity Stat
        self.stat_capacity = self._create_stat_item("Max Capacity:", "0 KB", "#e0e0e0")
        layout.addWidget(self.stat_capacity)       
        
        return container
    
    def _update_stats(self, image_path=None, payload_size=0):
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
            
    def _build_execution_group(self, button_text):
        container = QWidget()
        container.setMinimumHeight(60)
        container.setMaximumHeight(80)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        
        self.btn_exec = QPushButton(button_text)
        self.btn_exec.setMinimumHeight(35)
        self.btn_exec.setStyleSheet(
            "font-weight: bold; font-size: 11pt; "
            "background-color: #2d5a75; border-radius: 4px; color: white;"
        )
        
        self.btn_savestg = QPushButton("Save stego")
        self.btn_savestg.setMinimumHeight(35)
        self.btn_savestg.setStyleSheet(
            "font-weight: bold; font-size: 11pt; "
            "background-color: #888; border-radius: 4px; color: white;"
        )
        self.btn_savestg.setEnabled(False)
        self.btn_savestg.hide()
        
        # Progress Bar for Standalone/Locomotive modes
        self.standalone_progress_bar = QProgressBar()
        self.standalone_progress_bar.setValue(0)
        self.standalone_progress_bar.setTextVisible(False)
        self.standalone_progress_bar.setFixedHeight(6)
        
        # Status Label for Standalone/Locomotive modes
        self.standalone_status_label = QLabel("Ready.")
        self.standalone_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.standalone_status_label.setStyleSheet("color: #888; font-size: 9pt;")
        
        # Initial visibility check based on current mode
        # is_configurable = self.mode_combo.currentText() == "Configurable Model"
        # self.standalone_progress_bar.setVisible(not is_configurable)
        # self.standalone_status_label.setVisible(not is_configurable)

        self.btn_exec.clicked.connect(
            lambda: self._on_run_embed()
        )
        
        # 2. สร้าง Layout แนวนอนสำหรับปุ่ม
        hlayout = QHBoxLayout() 
        hlayout.setSpacing(10)
        hlayout.addWidget(self.btn_exec)
        hlayout.addWidget(self.btn_savestg)

        # 3. ยัด Layout ปุ่ม ลงใน Layout หลัก
        layout.addLayout(hlayout)
        layout.addWidget(self.standalone_progress_bar)
        layout.addWidget(self.standalone_status_label)
        
        return container
    
    def _on_save_stego(self, stego_rgb, metrics):
        try:
            orig_name = os.path.splitext(os.path.basename(self.current_image_path))[0]
            default_save_name = f"{orig_name}_stego.png"
            
            save_path, _ = QFileDialog.getSaveFileName(
                self, 
                "Save Stego Image", 
                default_save_name, 
                "PNG Images (*.png)"
            )

            if save_path:
                if Image: 
                    # แปลง Array กลับเป็นรูปแล้วบันทึก
                    final_image = Image.fromarray(stego_rgb)
                    final_image.save(save_path)

                    # แสดงผลลัพธ์
                    info_msg = (
                        f"Embedding Completed Successfully!\n\n"
                        f"--- Quality Metrics ---\n"
                        f"PSNR: {metrics.psnr:.2f} dB\n"
                        f"SSIM: {metrics.ssim:.4f}\n"
                        f"Drift: {metrics.hist_drift:.4f}\n"
                        f"Saved to: {save_path}"
                    )
                    QMessageBox.information(self, "Success", info_msg)
                    self.standalone_status_label.setText("Saved successfully.")
                else:
                    QMessageBox.critical(self, "Error", "PIL library missing.")
            else:
                self.standalone_status_label.setText("Save cancelled.")

        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Error during saving:\n{str(e)}")
    
    def _on_preview_image_dropped(self, file_path):
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
            self.current_image_path = file_path
            self.carrier_edit.setText(file_path)
            self._load_image_preview(file_path)
            
            # อัปเดต Stats เบื้องต้น
            payload_size = self._update_payload_size()
            self._update_stats(file_path, payload_size)
            self.update_capacity_indicator()
            
            # เริ่มคำนวณความจุละเอียด (Worker จะมาอัปเดต UI อีกทีเมื่อเสร็จ)
            self._start_capacity_calculation(file_path)
            
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image:\n{str(e)}")
                    
    def _create_stat_item(self, label_text, value_text, color):
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