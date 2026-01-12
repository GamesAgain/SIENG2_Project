import os

# --- PyQt6 Core ---
from PyQt6.QtCore import Qt, pyqtSignal, QSize

# --- PyQt6 GUI (Events & Images) ---
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QPixmap

# --- PyQt6 Widgets ---
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QStackedWidget, 
    QPushButton, QFileDialog, QStyle
)

# --- Local Utils (ฟังก์ชันตัดคำและแปลงหน่วยขนาดไฟล์) ---
from app.utils.file_io import truncate_filename, format_file_size
class AttachmentDropWidget(QWidget):
    """Modern drag & drop widget for file attachment with visual preview."""
    
    fileSelected = pyqtSignal(str)
    fileCleared = pyqtSignal()
    # Signal requested when the internal Browse button is pressed and
    # the parent wants to handle the actual file selection dialog.
    requestBrowse = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_path = None
        self.original_pixmap = None
        self._init_ui()
        self._set_empty_state()
        
        self.setAcceptDrops(True)
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        
        self.stack = QStackedWidget()
        self.stack.addWidget(self._create_empty_widget())
        self.stack.addWidget(self._create_loaded_widget())
        
        layout.addWidget(self.stack, 1)
        
        self.browse_btn = QPushButton("Browse Files")
        self.browse_btn.setMinimumHeight(32)
        # Emit a request signal so the parent (`EmbedTab`) can open
        # its own file dialog (and apply technique-specific filters).
        # Parent should connect `requestBrowse` to `browse_payload_file`.
        self.browse_btn.clicked.connect(self.requestBrowse.emit)
        layout.addWidget(self.browse_btn, 0)
    
    def _create_empty_widget(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.empty_label = QLabel("Drag & Drop\n(DOCX, ZIP, TXT, ...)")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(
            "border: 2px dashed #555; background-color: #222; "
            "color: #888; font-size: 14px;"
        )
        
        layout.addWidget(self.empty_label)
        return widget
    
    def _create_loaded_widget(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        
        self.icon_container = QLabel()
        self.icon_container.setMinimumSize(60, 60)
        self.icon_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_container.setScaledContents(False)
        
        self.filename_label = QLabel()
        self.filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.filesize_label = QLabel()
        self.filesize_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(self.icon_container, 1, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.filename_label, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.filesize_label, 0, Qt.AlignmentFlag.AlignCenter)
        
        return widget
    
    def _update_icon_size(self):
        """Update icon size based on container dimensions."""
        if self.original_pixmap is None:
            return
        
        container_size = self.icon_container.size()
        if container_size.width() <= 0 or container_size.height() <= 0:
            container_size = QSize(72, 72)
        
        max_size = min(container_size.width(), container_size.height()) - 8
        if max_size < 40:
            max_size = 40
        
        scaled_pixmap = self.original_pixmap.scaled(
            max_size, max_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.icon_container.setPixmap(scaled_pixmap)
    
    def resizeEvent(self, a0):
        """Handle resize events to update icon scaling."""
        super().resizeEvent(a0)
        if self.original_pixmap is not None and self.file_path:
            self._update_icon_size()
    
    def _set_empty_state(self):
        self.stack.setCurrentIndex(0)
        self.setStyleSheet("""
            AttachmentDropWidget {
                border: 2px dashed #555;
                border-radius: 8px;
                background-color: #1a1a1a;
            }
        """)
    
    def _set_loaded_state(self):
        self.stack.setCurrentIndex(1)
        self.setStyleSheet("""
            AttachmentDropWidget {
                border: 2px solid #3daee9;
                border-radius: 8px;
                background-color: #1e2a36;
            }
        """)
    
    def _browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select File", "", "All Files (*)"
        )
        if file_path:
            self.set_file(file_path)
    
    def set_file(self, file_path):
        if not file_path or not os.path.isfile(file_path):
            return
        
        self.file_path = file_path
        
        try:
            self._update_preview(file_path)
            self._set_loaded_state()
            self.fileSelected.emit(file_path)
        except Exception as e:
            print(f"Error loading file preview: {e}")
            self.clear_file()
    
    def _update_preview(self, file_path):
        pixmap = QPixmap(file_path)
        if not pixmap.isNull():
            self.original_pixmap = pixmap
            self._update_icon_size()
        else:
            self.original_pixmap = None
            file_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
            icon_pixmap = file_icon.pixmap(72, 72)
            self.icon_container.setPixmap(icon_pixmap)
        
        self.icon_container.setStyleSheet("""
            background-color: #2b2b2b;
            border: 1px solid #444;
            border-radius: 6px;
        """)
        
        filename = os.path.basename(file_path)
        truncated = truncate_filename(filename, 20)
        self.filename_label.setText(truncated)
        self.filename_label.setToolTip(filename)
        self.filename_label.setStyleSheet("""
            font-size: 10pt;
            color: #e0e0e0;
            font-weight: bold;
            background-color: transparent;
            border: none;
            padding: 2px;
        """)
        
        try:
            size_bytes = os.path.getsize(file_path)
            size_text = format_file_size(size_bytes)
        except OSError:
            size_text = "Unknown size"
        
        self.filesize_label.setText(size_text)
        self.filesize_label.setStyleSheet("""
            font-size: 8pt;
            color: #777;
            background-color: transparent;
            border: none;
        """)
    
    def clear_file(self):
        self.file_path = None
        self.original_pixmap = None
        self._set_empty_state()
        self.fileCleared.emit()
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("""
                AttachmentDropWidget {
                    border: 2px dashed #3daee9;
                    border-radius: 8px;
                    background-color: #1a1a1a;
                }
            """)
    
    def dragLeaveEvent(self, event):
        if self.file_path:
            self._set_loaded_state()
        else:
            self._set_empty_state()
    
    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                if os.path.isfile(file_path):
                    self.set_file(file_path)
        
        if self.file_path:
            self._set_loaded_state()
        else:
            self._set_empty_state()
    
    def get_file_path(self):
        return self.file_path
    
    def is_empty(self):
        return self.file_path is None