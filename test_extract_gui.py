import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QComboBox, 
    QTextEdit, QFileDialog, QMessageBox, QGroupBox, QFormLayout
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt

# Import LSBPP Engine
try:
    from app.core.stego.lsb_plus.lsbpp import LSBPP
except ImportError:
    # Fallback กรณีรันใน subfolder
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from app.core.stego.lsb_plus.lsbpp import LSBPP

class ExtractionWorker(QThread):
    """
    Worker Thread สำหรับรันกระบวนการถอดรหัสใน Background
    """
    finished_signal = pyqtSignal(str)  # ส่งผลลัพธ์ (Payload Text)
    error_signal = pyqtSignal(str)     # ส่ง Error Message
    log_signal = pyqtSignal(str)       # ส่ง Log ความคืบหน้า

    def __init__(self, stego_path, mode, password, key_path):
        super().__init__()
        self.stego_path = stego_path
        self.mode = mode
        self.password = password
        self.key_path = key_path

    def run(self):
        try:
            engine = LSBPP()

            def status_callback(text, percent):
                self.log_signal.emit(f"[{percent}%] {text}")

            self.log_signal.emit(f"Start extracting from: {os.path.basename(self.stego_path)}")
            self.log_signal.emit(f"Mode: {self.mode}")
            
            if self.mode == "public" and self.password:
                self.log_signal.emit("Info: Using provided password for Private Key.")

            # เรียกใช้ฟังก์ชัน extract
            # parameter 'password' ในโหมด public จะถูกใช้เป็น 'private_key_password' อัตโนมัติใน LSBPP.extract
            payload = engine.extract(
                stego_path=self.stego_path,
                encrypt_mode=self.mode,
                password=self.password, 
                private_key_path=self.key_path,
                status_callback=status_callback
            )

            self.finished_signal.emit(payload)

        except Exception as e:
            # import traceback
            # traceback.print_exc() 
            self.error_signal.emit(str(e))

class ExtractTestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LSB++ Extraction Tester (With Private Key Password)")
        self.resize(600, 700)
        self.setStyleSheet("""
            QWidget { font-size: 14px; font-family: Segoe UI, sans-serif; }
            QLineEdit { padding: 5px; border: 1px solid #ccc; border-radius: 3px; }
            QPushButton { padding: 8px; background-color: #0078d7; color: white; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #005a9e; }
            QPushButton:disabled { background-color: #ccc; }
            QGroupBox { font-weight: bold; margin-top: 10px; }
            QTextEdit { background-color: #f0f0f0; border: 1px solid #ddd; }
        """)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # --- Section 1: Image Input ---
        img_group = QGroupBox("1. Select Stego Image")
        img_layout = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Path to stego PNG image...")
        self.path_edit.setReadOnly(True)
        btn_browse_img = QPushButton("Browse Image")
        btn_browse_img.clicked.connect(self.browse_image)
        img_layout.addWidget(self.path_edit)
        img_layout.addWidget(btn_browse_img)
        img_group.setLayout(img_layout)
        layout.addWidget(img_group)

        # --- Section 2: Decryption Config ---
        config_group = QGroupBox("2. Decryption Settings")
        form_layout = QFormLayout()
        
        # Mode Selection
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Password (Symmetric)", "Public Key (Asymmetric)", "None (Plain)"])
        self.combo_mode.currentIndexChanged.connect(self.update_ui_state)
        form_layout.addRow("Encryption Mode:", self.combo_mode)

        # Private Key Input (ย้าย Private Key มาไว้ก่อน Password เพื่อความ Make Sense)
        self.key_path_edit = QLineEdit()
        self.key_path_edit.setPlaceholderText("Path to PRIVATE key (.pem)...")
        self.btn_browse_key = QPushButton("Browse Key")
        self.btn_browse_key.setFixedWidth(100)
        self.btn_browse_key.clicked.connect(self.browse_key)
        
        self.key_layout_widget = QWidget()
        key_layout = QHBoxLayout(self.key_layout_widget)
        key_layout.setContentsMargins(0,0,0,0)
        key_layout.addWidget(self.key_path_edit)
        key_layout.addWidget(self.btn_browse_key)
        
        self.lbl_key = QLabel("Private Key:")
        form_layout.addRow(self.lbl_key, self.key_layout_widget)

        # Password Input (ปรับให้ Label เปลี่ยนได้)
        self.lbl_pwd = QLabel("Password:") # เก็บตัวแปรไว้เปลี่ยนข้อความ
        self.pwd_edit = QLineEdit()
        self.pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_edit.setPlaceholderText("Enter password...")
        
        # เพิ่มปุ่มตาดูรหัสผ่าน
        self.btn_toggle_eye = QPushButton("👁")
        self.btn_toggle_eye.setFixedWidth(30)
        self.btn_toggle_eye.setCheckable(True)
        self.btn_toggle_eye.setStyleSheet("background: transparent; color: black; border: none; font-size: 16px;")
        self.btn_toggle_eye.clicked.connect(self.toggle_password_view)

        pwd_layout = QHBoxLayout()
        pwd_layout.addWidget(self.pwd_edit)
        pwd_layout.addWidget(self.btn_toggle_eye)

        form_layout.addRow(self.lbl_pwd, pwd_layout)

        config_group.setLayout(form_layout)
        layout.addWidget(config_group)

        # --- Section 3: Action ---
        self.btn_run = QPushButton("🚀 Run Extraction")
        self.btn_run.setMinimumHeight(45)
        self.btn_run.clicked.connect(self.start_extraction)
        layout.addWidget(self.btn_run)

        # --- Section 4: Output Log & Result ---
        res_group = QGroupBox("3. Result & Logs")
        res_layout = QVBoxLayout()
        
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setPlaceholderText("Process logs will appear here...")
        
        self.result_area = QTextEdit()
        self.result_area.setReadOnly(True)
        self.result_area.setStyleSheet("color: #2e7d32; font-weight: bold; background-color: #e8f5e9;")
        self.result_area.setPlaceholderText("Decrypted payload will appear here...")
        self.result_area.setMaximumHeight(100)

        res_layout.addWidget(QLabel("Process Log:"))
        res_layout.addWidget(self.log_area)
        res_layout.addWidget(QLabel("Decrypted Message:"))
        res_layout.addWidget(self.result_area)
        res_group.setLayout(res_layout)
        layout.addWidget(res_group)

        # Init state
        self.update_ui_state()

    def toggle_password_view(self, checked):
        if checked:
            self.pwd_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)

    def update_ui_state(self):
        mode_idx = self.combo_mode.currentIndex()
        # 0: Password, 1: Public Key, 2: None
        
        # การจัดการช่อง Password และ Key Path
        if mode_idx == 0: # Symmetric
            self.lbl_pwd.setText("Encryption Password:")
            self.pwd_edit.setPlaceholderText("Enter password used for encryption...")
            self.pwd_edit.setEnabled(True)
            self.pwd_edit.clear()
            
            self.lbl_key.setVisible(False)
            self.key_layout_widget.setVisible(False)

        elif mode_idx == 1: # Asymmetric (Public Key)
            self.lbl_pwd.setText("Private Key Password:")
            self.pwd_edit.setPlaceholderText("Enter password if key is encrypted (Optional)...")
            self.pwd_edit.setEnabled(True) # [FIX] ต้อง Enable ให้กรอกได้
            self.pwd_edit.clear()
            
            self.lbl_key.setVisible(True)
            self.key_layout_widget.setVisible(True)

        else: # None
            self.lbl_pwd.setText("Password:")
            self.pwd_edit.clear()
            self.pwd_edit.setEnabled(False)
            
            self.lbl_key.setVisible(False)
            self.key_layout_widget.setVisible(False)

    def browse_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Stego Image", "", "PNG Images (*.png)")
        if path:
            self.path_edit.setText(path)
            self.log_area.append(f"Selected Image: {path}")

    def browse_key(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Private Key", "", "PEM Files (*.pem);;All Files (*)")
        if path:
            self.key_path_edit.setText(path)

    def start_extraction(self):
        stego_path = self.path_edit.text()
        if not stego_path or not os.path.exists(stego_path):
            QMessageBox.warning(self, "Error", "Please select a valid stego image file.")
            return

        idx = self.combo_mode.currentIndex()
        mode_str = "password" if idx == 0 else "public" if idx == 1 else "none"
        pwd = self.pwd_edit.text()
        key_path = self.key_path_edit.text()

        # Validation Logic
        if idx == 0 and not pwd:
            QMessageBox.warning(self, "Error", "Please enter the encryption password.")
            return
        if idx == 1 and not key_path:
            QMessageBox.warning(self, "Error", "Please select a Private Key file.")
            return
        # Note: idx == 1 ไม่ต้องเช็ค pwd เพราะไฟล์ key อาจจะไม่ติดรหัสก็ได้ (Optional)

        # Disable UI
        self.btn_run.setEnabled(False)
        self.log_area.clear()
        self.result_area.clear()

        # Start Worker
        self.worker = ExtractionWorker(stego_path, mode_str, pwd, key_path)
        self.worker.log_signal.connect(self.log_area.append)
        self.worker.error_signal.connect(self.on_error)
        self.worker.finished_signal.connect(self.on_success)
        self.worker.start()

    def on_error(self, msg):
        self.log_area.append(f"<font color='red'>❌ ERROR: {msg}</font>")
        
        if "Bad decrypt" in msg or "mac check failed" in msg:
             self.log_area.append("<font color='orange'>Tip: Check your password again.</font>")
             
        QMessageBox.critical(self, "Extraction Failed", msg)
        self.btn_run.setEnabled(True)

    def on_success(self, payload):
        self.log_area.append("<font color='green'>✅ Extraction Successful!</font>")
        self.result_area.setPlainText(payload)
        self.btn_run.setEnabled(True)
        QMessageBox.information(self, "Success", "Payload extracted successfully!")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ExtractTestWindow()
    window.show()
    sys.exit(app.exec())