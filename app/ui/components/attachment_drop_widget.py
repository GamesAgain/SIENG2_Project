import os

# --- PyQt6 Core ---
from PyQt6.QtCore import Qt, pyqtSignal, QSize

# --- PyQt6 GUI (Events & Images) ---
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QPixmap

# --- PyQt6 Widgets ---
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget, 
    QPushButton, QFileDialog, QStyle, QFrame
)

# --- Local Utils ---
from app.utils.file_io import truncate_filename, format_file_size

class AttachmentDropWidget(QWidget):
    """drag & drop widget for file attachment with visual preview."""
    
    fileSelected = pyqtSignal(str)
    fileCleared = pyqtSignal()
    requestBrowse = pyqtSignal()
    
    def __init__(self, parent=None, allowed_extensions=None):
        super().__init__(parent)
        self.file_path = None
        self.original_pixmap = None
        self.allowed_extensions = allowed_extensions  # None = accept all, List = specific extensions
        self._original_style = ""  # For drag feedback
        self._init_ui()
        self._set_empty_state()
        
        
        self.setAcceptDrops(True)
    
    def set_allowed_extensions(self, extensions):
        """Update allowed extensions dynamically"""
        self.allowed_extensions = extensions
        
    def clear_allowed_extensions(self, extensions):
        """Clear allowed extensions dynamically"""
        self.allowed_extensions = None
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # Create a specific frame for the drop zone
        self.drop_frame = QFrame()
        self.drop_frame.setObjectName("drop_frame")
        self.drop_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        drop_layout = QVBoxLayout(self.drop_frame)
        drop_layout.setContentsMargins(0, 0, 0, 0)
        
        self.stack = QStackedWidget()
        self.stack.addWidget(self._create_empty_widget())
        self.stack.addWidget(self._create_loaded_widget())
        
        drop_layout.addWidget(self.stack)
        
        # Add drop frame to main layout
        layout.addWidget(self.drop_frame, 1)
        
        self.browse_btn = QPushButton("Browse Files")
        self.browse_btn.setMinimumHeight(32)
        self.browse_btn.clicked.connect(self.requestBrowse.emit)
        layout.addWidget(self.browse_btn, 0)
    
    def _create_empty_widget(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5) # Reduced from 6 to 2
        
        self.empty_label = QLabel("Drag & Drop\n(DOCX, ZIP, TXT, ...)")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(
            "border: none; background-color: transparent; "
            "color: #888; font-size: 14px;"
        )
        
        layout.addWidget(self.empty_label)
        return widget
    
    def _create_loaded_widget(self):
        widget = QWidget()
        
        main_layout = QHBoxLayout(widget)
        main_layout.setContentsMargins(10, 8, 10, 8) 
        main_layout.setSpacing(10)
        
        # --- ส่วนที่ 1: รูปภาพ/ไอคอน (ซ้าย) ---
        self.icon_container = QLabel()
        self.icon_container.setFixedSize(54, 54)
        self.icon_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_container.setScaledContents(False)
        self.icon_container.setStyleSheet("""
            QLabel {
                background-color: #2b2b2b;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 2px;
            }
        """)
        
        # --- ส่วนที่ 2: ข้อความรายละเอียด (ขวา) ---
        text_container = QWidget()
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2) 
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        self.filename_label = QLabel()
        self.filename_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.filename_label.setStyleSheet("""
            font-size: 10pt;
            font-weight: bold;
            color: #e0e0e0;
            border: none;
        """)
        
        self.filesize_label = QLabel()
        self.filesize_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.filesize_label.setStyleSheet("""
            font-size: 9pt;
            color: #888;
            border: none;
        """)
        
        text_layout.addWidget(self.filename_label)
        text_layout.addWidget(self.filesize_label)
        
        main_layout.addWidget(self.icon_container)
        main_layout.addWidget(text_container, 1)
        
        return widget
    
    def _update_icon_size(self):
        """Update icon size to fit fixed container."""
        if self.original_pixmap is None:
            return
        
        target_size = 46 
        
        scaled_pixmap = self.original_pixmap.scaled(
            target_size, target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.icon_container.setPixmap(scaled_pixmap)
    
    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        if self.original_pixmap is not None and self.file_path:
            self._update_icon_size()
    
    def _set_empty_state(self):
        self.stack.setCurrentIndex(0)
        empty_style = """
            QFrame#drop_frame {
                border: 2px dashed #555;
                border-radius: 4px;
                background-color: #222;
            }
        """
        self.drop_frame.setStyleSheet(empty_style)
        # Save for drag feedback
        self._original_style = empty_style
    
    def _set_loaded_state(self):
        self.stack.setCurrentIndex(1)
        loaded_style = """
            QFrame#drop_frame {
                border: 1px solid #444
                border-radius: 8px;
                background-color: #222;
            }
        """
        self.drop_frame.setStyleSheet(loaded_style)
        # Save for future drag feedback
        self._original_style = loaded_style
    
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
        else:
            self.original_pixmap = None
            file_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
            icon_pixmap = file_icon.pixmap(48, 48)
            self.icon_container.setPixmap(icon_pixmap)
        
        self._update_icon_size()
        
        filename = os.path.basename(file_path)
        truncated = truncate_filename(filename, 30)
        
        self.filename_label.setText(truncated)
        self.filename_label.setToolTip(filename)
        
        try:
            size_bytes = os.path.getsize(file_path)
            size_text = format_file_size(size_bytes)
        except OSError:
            size_text = "Unknown size"
        
        self.filesize_label.setText(size_text)
    
    def clear_file(self):
        self.file_path = None
        self.original_pixmap = None
        self._set_empty_state()
        self.fileCleared.emit()
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1:
                file_path = urls[0].toLocalFile()
                
                # Validate file type if allowed_extensions is set
                if self.allowed_extensions is not None:
                    ext = os.path.splitext(file_path)[1].lower()
                    if ext not in self.allowed_extensions:
                        event.ignore()
                        return
                
                event.acceptProposedAction()
                
                # Visual feedback - use regex for robust replacement
                import re
                self._original_style = self.drop_frame.styleSheet()
                new_style = re.sub(
                    r'border:\s*2px\s+dashed\s+#555', 
                    'border: 2px dashed #3daee9', 
                    self._original_style,
                    flags=re.IGNORECASE
                )
                self.drop_frame.setStyleSheet(new_style)
                return
        
        event.ignore()
    
    def dragLeaveEvent(self, event):
        # Restore original style
        if self._original_style:
            self.drop_frame.setStyleSheet(self._original_style)
    
    def dropEvent(self, event: QDropEvent):
        success = False
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                if os.path.isfile(file_path):
                    self.set_file(file_path)
                    success = True
        
        # Restore original style ONLY if drop was not successful
        # (If successful, set_file -> _set_loaded_state already set the correct new style)
        if not success and self._original_style:
            self.drop_frame.setStyleSheet(self._original_style)
            
    def get_file_path(self):
        return self.file_path
    
    def is_empty(self):
        return self.file_path is None