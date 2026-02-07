import sys
import os
import struct

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QComboBox, 
    QTextEdit, QFileDialog, QMessageBox, QGroupBox, QFormLayout, 
    QStackedWidget, QListWidget
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt

# --- 1. Dynamic Imports ---
# พยายาม Import Engine ทั้งสองตัว
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from app.core.stego.lsb_plus.lsbpp import LSBPP
except ImportError:
    print("⚠️ Warning: Could not import LSBPP.")
    LSBPP = None

try:
    # ลอง import จาก engine หรือ locomotive ตามที่มี
    try:
        from app.core.stego.locomotive.engine import Locomotive
    except ImportError:
        from app.core.stego.locomotive.locomotive import Locomotive
except ImportError:
    print("⚠️ Warning: Could not import Locomotive.")
    Locomotive = None

# =========================================================
# 2. WORKER THREAD (รองรับ 2 โหมด)
# =========================================================
class ExtractionWorker(QThread):
    finished_signal = pyqtSignal(object) # ส่ง object (str หรือ bytes)
    error_signal = pyqtSignal(str)
    log_signal = pyqtSignal(str)

    def __init__(self, technique, paths, mode, password, key_path):
        super().__init__()
        self.technique = technique # "LSB++" or "Locomotive"
        self.paths = paths         # Single path (str) or List of paths (list)
        self.mode = mode
        self.password = password
        self.key_path = key_path

    def run(self):
        try:
            def status_callback(text, percent):
                self.log_signal.emit(f"[{percent}%] {text}")

            if self.technique == "LSB++":
                if not LSBPP: raise ImportError("LSBPP Engine not found")
                
                engine = LSBPP()
                self.log_signal.emit(f"Starting LSB++ extraction on: {os.path.basename(self.paths)}")
                
                # LSB++ extract คืนค่าเป็น String (Payload Text)
                payload = engine.extract(
                    stego_path=self.paths,
                    encrypt_mode=self.mode,
                    password=self.password, 
                    private_key_path=self.key_path,
                    status_callback=status_callback
                )
                self.finished_signal.emit(payload)

            elif self.technique == "Locomotive":
                if not Locomotive: raise ImportError("Locomotive Engine not found")
                
                engine = Locomotive()
                self.log_signal.emit(f"Starting Locomotive extraction on {len(self.paths)} files...")
                
                # Locomotive extract คืนค่าเป็น Bytes (File Content)
                payload_bytes = engine.extract(
                    stego_paths=self.paths,
                    encrypt_mode=self.mode,
                    password=self.password, 
                    private_key_path=self.key_path,
                    status_callback=status_callback
                )
                self.finished_signal.emit(payload_bytes)

        except Exception as e:
            self.error_signal.emit(str(e))

# =========================================================
# 3. MAIN GUI WINDOW
# =========================================================
class ExtractTestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Steganography Extraction Tester (LSB++ & Locomotive)")
        self.resize(600, 750)
        self.stego_files_loco = [] # เก็บลิสต์ไฟล์สำหรับ Loco
        
        self.setStyleSheet("""
            QWidget { font-size: 14px; font-family: Segoe UI, sans-serif; }
            QLineEdit { padding: 5px; border: 1px solid #ccc; border-radius: 3px; }
            QPushButton { padding: 8px; background-color: #0078d7; color: white; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #005a9e; }
            QPushButton:disabled { background-color: #ccc; }
            QGroupBox { font-weight: bold; margin-top: 10px; }
            QTextEdit, QListWidget { background-color: #f0f0f0; border: 1px solid #ddd; }
        """)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # --- Section 0: Technique Selection ---
        tech_group = QGroupBox("1. Select Technique")
        tech_layout = QVBoxLayout()
        self.combo_tech = QComboBox()
        self.combo_tech.addItems(["LSB++", "Locomotive"])
        self.combo_tech.currentIndexChanged.connect(self.update_input_ui)
        tech_layout.addWidget(self.combo_tech)
        tech_group.setLayout(tech_layout)
        layout.addWidget(tech_group)

        # --- Section 1: Image Input (Stacked Widget) ---
        self.img_group = QGroupBox("2. Select Stego Image(s)")
        img_layout = QVBoxLayout()
        
        self.input_stack = QStackedWidget()
        
        # Page 0: LSB++ (Single File)
        page_lsb = QWidget()
        lsb_layout = QHBoxLayout(page_lsb)
        lsb_layout.setContentsMargins(0,0,0,0)
        self.path_edit_lsb = QLineEdit()
        self.path_edit_lsb.setPlaceholderText("Path to single PNG image...")
        self.path_edit_lsb.setReadOnly(True)
        btn_browse_lsb = QPushButton("Browse Image")
        btn_browse_lsb.clicked.connect(self.browse_lsb_image)
        lsb_layout.addWidget(self.path_edit_lsb)
        lsb_layout.addWidget(btn_browse_lsb)
        self.input_stack.addWidget(page_lsb)
        
        # Page 1: Locomotive (Multi File)
        page_loco = QWidget()
        loco_layout = QVBoxLayout(page_loco)
        loco_layout.setContentsMargins(0,0,0,0)
        self.file_list_loco = QListWidget()
        self.file_list_loco.setMaximumHeight(100)
        
        btn_row_loco = QHBoxLayout()
        btn_add_loco = QPushButton("Add Images")
        btn_add_loco.clicked.connect(self.browse_loco_images)
        btn_clear_loco = QPushButton("Clear")
        btn_clear_loco.setStyleSheet("background-color: #d9534f;")
        btn_clear_loco.clicked.connect(self.clear_loco_images)
        btn_row_loco.addWidget(btn_add_loco)
        btn_row_loco.addWidget(btn_clear_loco)
        
        loco_layout.addWidget(self.file_list_loco)
        loco_layout.addLayout(btn_row_loco)
        self.input_stack.addWidget(page_loco)
        
        img_layout.addWidget(self.input_stack)
        self.img_group.setLayout(img_layout)
        layout.addWidget(self.img_group)

        # --- Section 2: Decryption Config ---
        config_group = QGroupBox("3. Decryption Settings")
        form_layout = QFormLayout()
        
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Password (Symmetric)", "Public Key (Asymmetric)", "None (Plain)"])
        self.combo_mode.currentIndexChanged.connect(self.update_enc_ui)
        form_layout.addRow("Encryption Mode:", self.combo_mode)

        # Private Key
        self.key_path_edit = QLineEdit()
        self.key_path_edit.setPlaceholderText("Path to PRIVATE key (.pem)...")
        self.btn_browse_key = QPushButton("Browse Key")
        self.btn_browse_key.setFixedWidth(100)
        self.btn_browse_key.clicked.connect(self.browse_key)
        
        self.key_widget = QWidget()
        key_layout = QHBoxLayout(self.key_widget)
        key_layout.setContentsMargins(0,0,0,0)
        key_layout.addWidget(self.key_path_edit)
        key_layout.addWidget(self.btn_browse_key)
        
        self.lbl_key = QLabel("Private Key:")
        form_layout.addRow(self.lbl_key, self.key_widget)

        # Password
        self.lbl_pwd = QLabel("Password:")
        self.pwd_edit = QLineEdit()
        self.pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_edit.setPlaceholderText("Enter password...")
        self.btn_eye = QPushButton("👁")
        self.btn_eye.setFixedWidth(30)
        self.btn_eye.setCheckable(True)
        self.btn_eye.setStyleSheet("background: transparent; color: black; border: none; font-size: 16px;")
        self.btn_eye.clicked.connect(self.toggle_password_view)
        
        pwd_layout = QHBoxLayout()
        pwd_layout.addWidget(self.pwd_edit)
        pwd_layout.addWidget(self.btn_eye)
        form_layout.addRow(self.lbl_pwd, pwd_layout)

        config_group.setLayout(form_layout)
        layout.addWidget(config_group)

        # --- Section 3: Action ---
        self.btn_run = QPushButton("🚀 Run Extraction")
        self.btn_run.setMinimumHeight(45)
        self.btn_run.clicked.connect(self.start_extraction)
        layout.addWidget(self.btn_run)

        # --- Section 4: Result ---
        res_group = QGroupBox("4. Result & Logs")
        res_layout = QVBoxLayout()
        
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(100)
        self.log_area.setPlaceholderText("Logs...")
        
        self.result_area = QTextEdit()
        self.result_area.setReadOnly(True)
        self.result_area.setStyleSheet("color: #2e7d32; font-weight: bold; background-color: #e8f5e9;")
        self.result_area.setPlaceholderText("Decrypted text (LSB++) will appear here.")
        
        res_layout.addWidget(QLabel("Process Log:"))
        res_layout.addWidget(self.log_area)
        res_layout.addWidget(QLabel("Decrypted Output:"))
        res_layout.addWidget(self.result_area)
        res_group.setLayout(res_layout)
        layout.addWidget(res_group)

        # Init state
        self.update_input_ui()
        self.update_enc_ui()

    # --- UI Logic ---
    def update_input_ui(self):
        """สลับหน้าจอ Input ตาม Technique"""
        tech = self.combo_tech.currentText()
        if tech == "LSB++":
            self.input_stack.setCurrentIndex(0)
            self.img_group.setTitle("2. Select Stego Image (Single)")
            self.result_area.setPlaceholderText("Decrypted text will appear here.")
        else:
            self.input_stack.setCurrentIndex(1)
            self.img_group.setTitle("2. Select Stego Images (Multiple/Shards)")
            self.result_area.setPlaceholderText("Result is a file. You will be prompted to save it.")

    def update_enc_ui(self):
        """ซ่อน/แสดงช่องกรอกรหัสตามโหมด"""
        idx = self.combo_mode.currentIndex()
        # 0: Password, 1: Public Key, 2: None
        if idx == 0: # Symmetric
            self.lbl_pwd.setText("Encryption Password:")
            self.pwd_edit.setEnabled(True)
            self.lbl_key.setVisible(False)
            self.key_widget.setVisible(False)
        elif idx == 1: # Asymmetric
            self.lbl_pwd.setText("Key Password (Optional):")
            self.pwd_edit.setEnabled(True)
            self.lbl_key.setVisible(True)
            self.key_widget.setVisible(True)
        else: # None
            self.lbl_pwd.setText("Password:")
            self.pwd_edit.setEnabled(False)
            self.lbl_key.setVisible(False)
            self.key_widget.setVisible(False)

    def toggle_password_view(self, checked):
        self.pwd_edit.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)

    # --- Browsing ---
    def browse_lsb_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Stego Image", "", "PNG Images (*.png)")
        if path:
            self.path_edit_lsb.setText(path)
            self.log_area.append(f"Selected: {os.path.basename(path)}")

    def browse_loco_images(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Stego Images", "", "PNG Images (*.png)")
        if files:
            self.stego_files_loco.extend(files)
            self.stego_files_loco = list(set(self.stego_files_loco))
            self.refresh_loco_list()
            self.log_area.append(f"Added {len(files)} files.")

    def clear_loco_images(self):
        self.stego_files_loco = []
        self.refresh_loco_list()

    def refresh_loco_list(self):
        self.file_list_loco.clear()
        for p in self.stego_files_loco:
            self.file_list_loco.addItem(os.path.basename(p))

    def browse_key(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Private Key", "", "PEM Files (*.pem);;All Files (*)")
        if path:
            self.key_path_edit.setText(path)

    # --- Execution ---
    def start_extraction(self):
        tech = self.combo_tech.currentText()
        
        # 1. Validate Input Paths
        target_paths = None
        if tech == "LSB++":
            path = self.path_edit_lsb.text()
            if not path or not os.path.exists(path):
                QMessageBox.warning(self, "Error", "Please select a valid image.")
                return
            target_paths = path # String
        else:
            if not self.stego_files_loco:
                QMessageBox.warning(self, "Error", "Please select at least one image.")
                return
            target_paths = self.stego_files_loco # List

        # 2. Get Config
        idx = self.combo_mode.currentIndex()
        mode_str = "password" if idx == 0 else "public" if idx == 1 else "none"
        pwd = self.pwd_edit.text()
        key_path = self.key_path_edit.text()

        if idx == 0 and not pwd:
            QMessageBox.warning(self, "Error", "Password required.")
            return
        if idx == 1 and not key_path:
            QMessageBox.warning(self, "Error", "Private Key required.")
            return

        # 3. Run Worker
        self.btn_run.setEnabled(False)
        self.log_area.clear()
        self.result_area.clear()
        
        self.worker = ExtractionWorker(tech, target_paths, mode_str, pwd, key_path)
        self.worker.log_signal.connect(self.log_area.append)
        self.worker.error_signal.connect(self.on_error)
        self.worker.finished_signal.connect(lambda res: self.on_success(res, tech))
        self.worker.start()

    def on_error(self, msg):
        self.log_area.append(f"<font color='red'>❌ Error: {msg}</font>")
        QMessageBox.critical(self, "Failed", msg)
        self.btn_run.setEnabled(True)

    def on_success(self, result, tech):
        self.log_area.append("<font color='green'>✅ Extraction Successful!</font>")
        self.btn_run.setEnabled(True)
        
        if tech == "LSB++":
            # LSB++ returns String (Text)
            if isinstance(result, bytes): # กันพลาดเผื่อ engine คืน bytes
                try: result = result.decode('utf-8')
                except: result = str(result)
            self.result_area.setPlainText(result)
            QMessageBox.information(self, "Success", "Text extracted successfully!")
            
        else:
            # Locomotive returns Bytes (File)
            self.result_area.setPlainText(f"[Binary Data] {len(result)} bytes extracted.\nPlease save to file.")
            
            save_path, _ = QFileDialog.getSaveFileName(self, "Save Extracted File", "extracted_file", "All Files (*)")
            if save_path:
                try:
                    with open(save_path, 'wb') as f:
                        f.write(result)
                    self.log_area.append(f"Saved to: {save_path}")
                    QMessageBox.information(self, "Success", f"File saved to:\n{save_path}")
                except Exception as e:
                    QMessageBox.critical(self, "Save Error", str(e))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ExtractTestWindow()
    window.show()
    sys.exit(app.exec())