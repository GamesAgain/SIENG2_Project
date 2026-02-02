import os
import re
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

class MetadataDropWidget(QFrame): # เปลี่ยนมาใช้ QFrame
    fileDropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("drop_frame")
        self.setAcceptDrops(True)
        self._original_style = ""
        self._init_ui()
        self._set_default_style()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        self.label = QLabel("Drag & Drop File Here\n(PNG, JPG, MP3)")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("border: none; background: transparent; color: #aaa;")
        layout.addWidget(self.label)

    def _set_default_style(self):
        style = """
            QFrame#drop_frame {
                border: 2px dashed #555;
                background-color: #222;
                border-radius: 8px;
            }
        """
        self.setStyleSheet(style)
        self._original_style = style

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            file_path = event.mimeData().urls()[0].toLocalFile()
            ext = os.path.splitext(file_path)[1].lower()
            
            if ext in ['.png', '.jpg', '.jpeg', '.mp3']:
                event.acceptProposedAction()
                
                current_style = self.styleSheet()
                new_style = re.sub(r'#555', '#3daee9', current_style)
                self.setStyleSheet(new_style)
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._original_style)

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet(self._original_style) # คืนค่าสีเดิม
        file_path = event.mimeData().urls()[0].toLocalFile()
        self.label.setText(f"Selected:\n{os.path.basename(file_path)}")
        self.fileDropped.emit(file_path)