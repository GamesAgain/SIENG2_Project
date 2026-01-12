import os
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTabWidget, QLabel, QComboBox, QLineEdit, QPushButton, QTextEdit,
    QProgressBar, QGroupBox, QFileDialog, QListWidget, QGridLayout, 
    QStyle, QStackedWidget, QListWidgetItem, QDialog,
    QScrollArea, QFormLayout, QSplitter, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QPixmap, QFont, QDragEnterEvent, QDropEvent, QResizeEvent

from app.utils.file_io import  (truncate_filename, format_file_size)

# ============================================================================
# STYLE
# ============================================================================
TILE_CONTAINER_STYLE = """
    background-color: #1a1a1a;
    border: 2px solid #444;
    border-radius: 6px;
"""


class LocoFileTile(QWidget):
    """Display thumbnail, filename, and file size for Locomotive mode."""
    
    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        self.original_pixmap = None
        self._init_ui()
        self._load_pixmap()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        
        self.thumbnail_container = self._create_thumbnail()
        layout.addWidget(self.thumbnail_container, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._create_filename_label(), 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._create_filesize_label(), 0, Qt.AlignmentFlag.AlignCenter)

    def _load_pixmap(self):
        """Load and store the original pixmap for scaling."""
        pixmap = QPixmap(self.file_path)
        if not pixmap.isNull():
            self.original_pixmap = pixmap
        else:
            self.original_pixmap = None

    def _create_thumbnail(self):
        container = QLabel()
        container.setMinimumSize(60, 60)
        container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container.setStyleSheet(TILE_CONTAINER_STYLE)
        container.setScaledContents(False)
        
        if self.original_pixmap is None:
            container.setText("🖼️")
            container.setStyleSheet(TILE_CONTAINER_STYLE + "font-size: 32pt; color: #666;")
        else:
            self._update_thumbnail_size(container)
        
        return container
    
    def _update_thumbnail_size(self, container):
        """Update thumbnail size based on container dimensions."""
        if self.original_pixmap is None:
            return
        
        container_size = container.size()
        if container_size.width() <= 0 or container_size.height() <= 0:
            container_size = QSize(82, 82)
        
        max_size = min(container_size.width(), container_size.height()) - 8
        if max_size < 40:
            max_size = 40
        
        scaled_pixmap = self.original_pixmap.scaled(
            max_size, max_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        container.setPixmap(scaled_pixmap)
    
    def resizeEvent(self, a0):
        """Handle resize events to update thumbnail scaling."""
        super().resizeEvent(a0)
        if self.original_pixmap is not None:
            self._update_thumbnail_size(self.thumbnail_container)

    def _create_filename_label(self):
        filename = os.path.basename(self.file_path)
        label = QLabel(truncate_filename(filename))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            "font-size: 9pt; color: #bbb; background-color: transparent; "
            "border: none; padding: 2px;"
        )
        label.setWordWrap(True)
        label.setToolTip(filename)
        return label

    def _create_filesize_label(self):
        try:
            size_bytes = os.path.getsize(self.file_path)
            size_text = format_file_size(size_bytes)
        except OSError:
            size_text = ""
        
        label = QLabel(size_text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            "font-size: 7pt; color: #777; background-color: transparent; border: none;"
        )
        return label