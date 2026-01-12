from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QTextEdit, QHBoxLayout, QLabel, QPushButton)
from app.ui.styles import DARK_STYLE
class TextEditorDialog(QDialog):
    """Text Editor Dialog with real-time capacity tracking."""
    
    def __init__(self, initial_text="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Text Editor")
        self.resize(700, 500)
        self.setStyleSheet(DARK_STYLE)
        
        layout = QVBoxLayout(self)
        
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(initial_text)
        layout.addWidget(self.text_edit)
        
        status_bar = QHBoxLayout()
        
        self.lbl_cursor = QLabel("Ln: 1, Col: 1")
        self.lbl_cursor.setStyleSheet("color: #888;")
        
        self.lbl_capacity = QLabel("Capacity: 0/100")
        self.lbl_capacity.setStyleSheet("color: #aaa;")
        
        status_bar.addStretch()
        status_bar.addWidget(self.lbl_cursor)
        status_bar.addSpacing(20)
        status_bar.addWidget(self.lbl_capacity)
        
        layout.addLayout(status_bar)
        
        btn_save = QPushButton("Save & Close")
        btn_save.setMinimumHeight(40)
        btn_save.setStyleSheet("font-weight: bold; background-color: #2d5a75;")
        btn_save.clicked.connect(self.accept)
        layout.addWidget(btn_save)
        
        self.text_edit.cursorPositionChanged.connect(self.update_stats)
        self.text_edit.textChanged.connect(self.update_stats)
        
        self.update_stats()
        
    def update_stats(self):
        cursor = self.text_edit.textCursor()
        row = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self.lbl_cursor.setText(f"Ln: {row}, Col: {col}")
        
        text = self.text_edit.toPlainText()
        count = len(text)
        max_cap = 100
        self.lbl_capacity.setText(f"Capacity: {count}/{max_cap}")
        
        if count > max_cap:
            self.lbl_capacity.setStyleSheet("color: #ff5555; font-weight: bold;")
        else:
            self.lbl_capacity.setStyleSheet("color: #aaa;")

    def get_text(self):
        return self.text_edit.toPlainText()