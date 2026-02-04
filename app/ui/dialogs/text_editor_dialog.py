from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QTextEdit, QHBoxLayout, QLabel, QPushButton)
from app.ui.styles import DARK_STYLE
from app.utils.file_io import format_file_size  # อย่าลืม Import ตัวนี้

class TextEditorDialog(QDialog):
    """Text Editor Dialog with real-time capacity tracking (Formatted Size)."""
    
    def __init__(self, initial_text="", safe_limit=0, max_limit=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Text Editor Payload")
        self.resize(800, 600)
        self.setStyleSheet(DARK_STYLE)
        
        # เก็บค่า Limit ที่รับมาจากหน้าหลัก
        self.safe_limit = safe_limit
        self.max_limit = max_limit
        
        layout = QVBoxLayout(self)
        
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(initial_text)
        self.text_edit.setPlaceholderText("Type your secret message here...")
        layout.addWidget(self.text_edit)
        
        status_bar = QHBoxLayout()
        
        self.lbl_cursor = QLabel("Ln: 1, Col: 1")
        self.lbl_cursor.setStyleSheet("color: #888; font-family: monospace;")
        
        # ปรับ Default Text
        self.lbl_capacity = QLabel("Size: 0 B")
        self.lbl_capacity.setStyleSheet("color: #aaa; font-family: monospace; font-weight: bold;")
        
        status_bar.addWidget(self.lbl_cursor)
        status_bar.addStretch()
        status_bar.addWidget(self.lbl_capacity)
        
        layout.addLayout(status_bar)
        
        btn_save = QPushButton("Save & Close")
        btn_save.setMinimumHeight(40)
        btn_save.setStyleSheet("""
            QPushButton {
                font-weight: bold; 
                background-color: #2d5a75; 
                color: white;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #3daee9; }
            QPushButton:pressed { background-color: #1c3b4d; }
        """)
        btn_save.clicked.connect(self.accept)
        layout.addWidget(btn_save)
        
        # Signals
        self.text_edit.cursorPositionChanged.connect(self._update_cursor_pos)
        self.text_edit.textChanged.connect(self.update_stats)
        
        # Initial Update
        self._update_cursor_pos()
        self.update_stats()
        
    def _update_cursor_pos(self):
        cursor = self.text_edit.textCursor()
        row = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self.lbl_cursor.setText(f"Ln: {row}, Col: {col}")

    def update_stats(self):
        """Calculates size in bytes and updates UI with color coding."""
        # 1. คำนวณขนาดเป็น Bytes (สำคัญมาก: ต้อง encode utf-8 เพื่อความแม่นยำ)
        text_content = self.text_edit.toPlainText()
        current_size = len(text_content.encode('utf-8'))
        
        # กรณีไม่มีการคำนวณ Limit มาก่อน (เช่น ยังไม่ได้เลือกรูป)
        if self.max_limit == 0:
            self.lbl_capacity.setText(f"Size: {format_file_size(current_size)}")
            self.lbl_capacity.setStyleSheet("color: #aaa;")
            return

        # 2. สร้างข้อความแสดงผล
        cap_text = f"Capacity: {format_file_size(current_size)} / {format_file_size(self.safe_limit)}"
        
        # 3. ตรวจสอบเงื่อนไขสี (Logic เดียวกับหน้า EmbedTab)
        if current_size <= self.safe_limit:
            # SAFE (สีเทา/ปกติ)
            self.lbl_capacity.setStyleSheet("color: #aaa;")
            
        elif current_size <= self.max_limit:
            # RISK (สีส้ม)
            self.lbl_capacity.setStyleSheet("color: #ffaa00; font-weight: bold;")
            cap_text += " (Risk)"
            
        else:
            # OVER LIMIT (สีแดง)
            self.lbl_capacity.setStyleSheet("color: #ff5555; font-weight: bold;")
            cap_text += " (Over Limit)"
            
        self.lbl_capacity.setText(cap_text)

    def get_text(self):
        return self.text_edit.toPlainText()