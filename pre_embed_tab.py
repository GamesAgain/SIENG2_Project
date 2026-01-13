#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PROTOTYPE: Redesigned Embed Tab - Desktop Application Style
Refined version without web-style elements (no emojis, appropriate sizing)
"""

# ============================================================================
# 1. STANDARD LIBRARY IMPORTS
# ============================================================================
import sys
import os
from datetime import datetime
from typing import Optional

from app.ui.styles import DARK_STYLE

# Mock imports for standalone testing
try:
    from app.core.stego.lsb_plus_engine.lsb_plus import LSB_Plus
    from app.utils.exceptions import StegoEngineError
    from app.utils.file_io import format_file_size
    MOCK_MODE = False
except ImportError:
    MOCK_MODE = True
    print("⚠️ Running in MOCK MODE - Core modules not found")
    
    class StegoEngineError(Exception):
        pass
    
    def format_file_size(size_bytes):
        """Mock file size formatter"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"

# ============================================================================
# 2. THIRD-PARTY LIBRARIES
# ============================================================================
try:
    from PIL import Image, ExifTags
except ImportError:
    Image = None
    ExifTags = None

try:
    import mutagen
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3
except ImportError:
    mutagen = None

try:
    import piexif
except ImportError:
    piexif = None

# ============================================================================
# 3. PYQT6 FRAMEWORK
# ============================================================================
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog, 
    QStackedWidget, QTabWidget, QGroupBox, QScrollArea,
    QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QSizePolicy,
    QPushButton, QLineEdit, QTextEdit, QComboBox,
    QLabel, QProgressBar, QListWidget, QListWidgetItem, QMessageBox,
    QFileDialog, QStyle, QFrame
)

# ============================================================================
# 4. LOCAL APPLICATION IMPORTS (with fallbacks)
# ============================================================================
try:
    from app.utils.gui_helpers import disconnect_signal_safely
    from app.ui.dialogs.text_editor_dialog import TextEditorDialog
    from app.ui.components.loco_file import LocoFileTile
    from app.ui.components.attachment_drop_widget import AttachmentDropWidget
except ImportError:
    def disconnect_signal_safely(signal):
        try:
            signal.disconnect()
        except:
            pass
    
    class TextEditorDialog(QDialog):
        def __init__(self, text, parent=None):
            super().__init__(parent)
            self.text = text
        def get_text(self):
            return self.text
    
    class LocoFileTile(QWidget):
        deleteRequested = pyqtSignal(str)
        def __init__(self, file_path):
            super().__init__()
            self.file_path = file_path
    
    class AttachmentDropWidget(QWidget):
        fileSelected = pyqtSignal(str)
        fileCleared = pyqtSignal()
        requestBrowse = pyqtSignal()
        
        def __init__(self):
            super().__init__()
            self.empty_label = QLabel("Drag & Drop")
            layout = QVBoxLayout(self)
            layout.addWidget(self.empty_label)
        
        def set_file(self, path):
            pass
        
        def clear_file(self):
            pass

# ============================================================================
# CONSTANTS & STYLES
# ============================================================================

PAGE_STANDALONE = 0
PAGE_LOCOMOTIVE = 1
PAGE_CONFIGURABLE = 2

TAB_INDEX_TEXT = 0
TAB_INDEX_FILE = 1

# Desktop-appropriate button styles
PRIMARY_BUTTON_STYLE = """
QPushButton {
    background-color: #2d5a75;
    border: 1px solid #3daee9;
    border-radius: 4px;
    padding: 8px 16px;
    color: white;
    font-weight: bold;
    font-size: 10pt;
}
QPushButton:hover {
    background-color: #3a6d8f;
    border: 1px solid #5ec8ff;
}
QPushButton:pressed {
    background-color: #1f4459;
}
QPushButton:disabled {
    background-color: #2a2a2a;
    border: 1px solid #555;
    color: #666;
}
"""

SUCCESS_BUTTON_STYLE = """
QPushButton {
    background-color: #2d7a3e;
    border: 1px solid #4caf50;
    border-radius: 4px;
    padding: 8px 16px;
    color: white;
    font-weight: bold;
    font-size: 10pt;
}
QPushButton:hover {
    background-color: #3a9450;
    border: 1px solid #66bb6a;
}
QPushButton:pressed {
    background-color: #1f5a2c;
}
"""

SECONDARY_BUTTON_STYLE = """
QPushButton {
    background-color: #3c3f41;
    border: 1px solid #666;
    border-radius: 4px;
    padding: 8px 16px;
    color: #bbb;
    font-size: 10pt;
}
QPushButton:hover {
    background-color: #4a4d4f;
    border: 1px solid #888;
    color: #fff;
}
"""


# ============================================================================
# MAIN EMBED TAB (REDESIGNED - DESKTOP STYLE)
# ============================================================================

class EmbedTab(QWidget):
    """Main embedding tab with REDESIGNED LSB++ Right Panel (Desktop Style)."""
    
    def __init__(self):
        super().__init__()
        self.current_image_path = None
        self.locomotive_files = []
        self.meta_fields = {}
        self.embed_pipeline = []
        self.extract_pipeline = []
        self.original_preview_pixmaps = {}
        
        # Track embedding state
        self.stego_data = None
        self.embed_completed = False
        
        self._init_ui()

    def _init_ui(self):
        self.setMinimumSize(800, 500)
        
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)

        left_panel = self._create_left_panel()
        self.right_panel_stack = self._create_right_panel()

        main_layout.addWidget(left_panel, 35)
        main_layout.addWidget(self.right_panel_stack, 65)

        self.on_technique_changed()

    def _create_left_panel(self):
        """Left panel - unchanged from original"""
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

    def _create_right_panel(self):
        """Right panel stack - with REDESIGNED standalone page"""
        stack = QStackedWidget()
        stack.addWidget(self._create_standalone_page_redesigned())
        stack.addWidget(self._create_locomotive_page())
        stack.addWidget(self._create_configurable_page())
        return stack

    # ========================================================================
    # REDESIGNED STANDALONE PAGE (LSB++ - DESKTOP STYLE)
    # ========================================================================
    
    def _create_standalone_page_redesigned(self):
        """
        REDESIGNED Right Panel - Matching Original Style
        Layout: Preview (top) → Buttons (bottom)
        """
        page = QWidget()
        page.setMinimumSize(400, 400)
        
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        
        # 1. PREVIEW AREA (Top - matches original)
        preview_group = self._build_preview_section_original()
        layout.addWidget(preview_group, 1)
        
        # 2. EXECUTION BUTTONS (Bottom - matches original)
        execution_group = self._build_execution_group_original()
        layout.addWidget(execution_group, 0)
        
        return page
    
    def _build_preview_section_original(self):
        """Preview section matching original style with stats"""
        group_box = QGroupBox("Preview")
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(6, 12, 6, 6)
        group_layout.setSpacing(6)
        
        # Preview Label
        self.preview_label_std = QLabel()
        self.preview_label_std.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label_std.setText("No Image Selected\n\nSelect cover image from left panel")
        self.preview_label_std.setStyleSheet("""
            QLabel {
                border: 2px dashed #555;
                background-color: #222;
                color: #888;
                font-size: 10pt;
            }
        """)
        self.preview_label_std.setMinimumHeight(200)
        self.preview_label_std.setScaledContents(False)
        group_layout.addWidget(self.preview_label_std, 1)
        
        # Info Label (file info)
        self.preview_info_label_std = QLabel("")
        self.preview_info_label_std.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_info_label_std.setStyleSheet("color: #e0e0e0; font-size: 9pt;")
        self.preview_info_label_std.hide()
        group_layout.addWidget(self.preview_info_label_std, 0)
        
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
        
        # Image Size Stat
        self.stat_image_size = self._create_stat_item("Image Size:", "No Image", "#e0e0e0")
        layout.addWidget(self.stat_image_size)
        
        # Max Capacity Stat
        self.stat_capacity = self._create_stat_item("Max Capacity:", "0 KB", "#e0e0e0")
        layout.addWidget(self.stat_capacity)
        
        # Payload Size Stat
        self.stat_payload = self._create_stat_item("Payload Size:", "0 KB", "#e0e0e0")
        layout.addWidget(self.stat_payload)
        
        return container
    
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
    
    def _build_execution_group_original(self):
        """Execution buttons matching original style"""
        container = QWidget()
        container.setMinimumHeight(100)
        container.setMaximumHeight(130)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        
        # Button Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        
        # Embed Button
        self.btn_embed = QPushButton("Embed Data")
        self.btn_embed.setMinimumHeight(45)
        self.btn_embed.setStyleSheet(
            "font-weight: bold; font-size: 11pt; "
            "background-color: #2d5a75; border-radius: 4px; color: white;"
        )
        self.btn_embed.clicked.connect(self._on_run_embed)
        
        # Save Button
        self.btn_save_stego = QPushButton("Save Stego Image")
        self.btn_save_stego.setMinimumHeight(45)
        self.btn_save_stego.setStyleSheet(
            "font-weight: bold; font-size: 11pt; "
            "background-color: #888; border-radius: 4px; color: white;"
        )
        self.btn_save_stego.setEnabled(False)
        self.btn_save_stego.clicked.connect(self._on_save_stego)
        
        btn_row.addWidget(self.btn_embed)
        btn_row.addWidget(self.btn_save_stego)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        
        # Status Label
        self.status_label = QLabel("Ready to embed data")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #888; font-size: 9pt;")
        
        layout.addLayout(btn_row)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        
        return container
    
    # ========================================================================
    # STATS UPDATE LOGIC
    # ========================================================================
    
    def _update_stats(self, image_path=None, payload_size=0):
        """Update stats display with current data"""
        if image_path and os.path.exists(image_path):
            try:
                with Image.open(image_path) as img:
                    width, height = img.size
                    
                    # Get file size
                    file_size = os.path.getsize(image_path)
                    file_size_str = format_file_size(file_size)
                    
                    # Update Image Size (with dimensions and file size)
                    self.stat_image_size.value_label.setText(f"{width}×{height} ({file_size_str})")
                    
                    # Calculate and update Max Capacity
                    capacity_bytes = (width * height * 3) // 8
                    capacity_str = format_file_size(capacity_bytes)
                    self.stat_capacity.value_label.setText(capacity_str)
                    
                    # Update Payload Size with color coding
                    payload_str = format_file_size(payload_size)
                    self.stat_payload.value_label.setText(payload_str)
                    
                    # Color code payload based on capacity
                    if payload_size > capacity_bytes:
                        self.stat_payload.value_label.setStyleSheet(
                            "color: #f44336; font-weight: bold; font-size: 9pt; background: transparent; border: none;"
                        )
                    elif payload_size > 0:
                        self.stat_payload.value_label.setStyleSheet(
                            "color: #4caf50; font-size: 9pt; background: transparent; border: none;"
                        )
                    else:
                        self.stat_payload.value_label.setStyleSheet(
                            "color: #e0e0e0; font-size: 9pt; background: transparent; border: none;"
                        )
                        
            except Exception as e:
                self.stat_image_size.value_label.setText("Error")
                self.stat_capacity.value_label.setText("N/A")
        else:
            self.stat_image_size.value_label.setText("No Image")
            self.stat_capacity.value_label.setText("0 KB")
            self.stat_payload.value_label.setText(format_file_size(payload_size))
    
    # ========================================================================
    # EMBED LOGIC
    # ========================================================================
    
    def _on_run_embed(self):
        """Handle embed button click"""
        if not self.current_image_path:
            QMessageBox.warning(self, "Missing Cover", "Please select a cover image.")
            return

        text = self.payload_text.toPlainText()
        if not text:
            QMessageBox.warning(self, "Empty Payload", "Please enter some text to embed.")
            return

        # Check encryption settings
        password = None
        public_key_path = None
        
        if self.encryption_box.isChecked():
            mode = self.enc_combo.currentData()
            if mode == "password":
                password = self.passphrase.text()
                confirm_password = self.confirmpassphrase.text()
                
                if not password:
                    QMessageBox.warning(self, "Missing Password", "Please enter a password.")
                    return
                
                if password != confirm_password:
                    QMessageBox.warning(self, 'Password Mismatch', 
                                      'Passwords do not match. Please try again.')
                    self.confirmpassphrase.clear()
                    self.confirmpassphrase.setFocus()
                    return
                    
            elif mode == "public":
                public_key_path = self.public_key_edit.text().strip()
                if not public_key_path:
                    QMessageBox.warning(self, "Missing Public Key", 
                                      "Please select a public key PEM file.")
                    return

        # Update UI to "processing" state
        self.btn_embed.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Encrypting payload...")
        QApplication.processEvents()
        
        # Simulate progress
        for i in range(0, 101, 20):
            self.progress_bar.setValue(i)
            QApplication.processEvents()
            QTimer.singleShot(100, lambda: None)
        
        try:
            if MOCK_MODE:
                self.status_label.setText("Mock embedding completed")
                self.stego_data = b"MOCK_STEGO_DATA"
                success = True
            else:
                lsb_engine = LSB_Plus()
                payload_text = self.payload_text.toPlainText()
                
                self.stego_data, metrics = lsb_engine.embed(
                    cover_path=self.current_image_path,
                    payload_text=payload_text,
                    mode=mode if self.encryption_box.isChecked() else None,
                    password=password,
                    public_key_path=public_key_path,
                    show_progress=False,
                )
                success = True
                
        except Exception as exc:
            QMessageBox.critical(self, "Embed Error", str(exc))
            self.status_label.setText("Error: embed failed")
            self._reset_embed_ui()
            return
        
        # Success state
        self.embed_completed = True
        self.progress_bar.setValue(100)
        self.status_label.setText("Embedding completed successfully!")
        
        # Update button states
        self.btn_embed.setEnabled(True)
        self.btn_save_stego.setEnabled(True)
        self.btn_save_stego.setStyleSheet(
            "font-weight: bold; font-size: 11pt; "
            "background-color: #2d7a3e; border-radius: 4px; color: white;"
        )
        
        QMessageBox.information(self, "Success", 
                              "Data embedded successfully!\nClick 'Save Stego Image' to export.")
    
    def _on_save_stego(self):
        """Handle save stego button click"""
        if not self.embed_completed or not self.stego_data:
            QMessageBox.warning(self, "No Data", "Please embed data first.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Stego Image", "", "PNG Images (*.png)"
        )
        
        if not file_path:
            return
        
        try:
            if MOCK_MODE:
                with open(file_path, 'wb') as f:
                    f.write(self.stego_data)
                QMessageBox.information(self, "Saved", f"Mock stego image saved to:\n{file_path}")
            else:
                QMessageBox.information(self, "Saved", f"Stego image saved to:\n{file_path}")
            
            self.status_label.setText(f"Saved: {os.path.basename(file_path)}")
            
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save file:\n{str(e)}")
    
    def _reset_embed_ui(self):
        """Reset UI to initial state"""
        self.embed_completed = False
        self.stego_data = None
        
        self.btn_embed.setEnabled(True)
        self.btn_save_stego.setEnabled(False)
        self.btn_save_stego.setStyleSheet(
            "font-weight: bold; font-size: 11pt; "
            "background-color: #888; border-radius: 4px; color: white;"
        )
        
        self.progress_bar.setValue(0)
        self.status_label.setText("Ready to embed data")

    # ========================================================================
    # ORIGINAL METHODS (Locomotive & Configurable - stubs)
    # ========================================================================
    
    def _create_locomotive_page(self):
        page = QWidget()
        label = QLabel("Locomotive Mode\n(Not implemented in prototype)")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(page)
        layout.addWidget(label)
        return page
    
    def _create_configurable_page(self):
        page = QWidget()
        label = QLabel("Configurable Mode\n(Not implemented in prototype)")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(page)
        layout.addWidget(label)
        return page

    # ========================================================================
    # LEFT PANEL BUILDERS
    # ========================================================================
    
    def _build_mode_section(self):
        return self._create_combo_group("Mode Selection", [
            ("Standalone", "Hide data using one specific method independently."),
            ("Configurable Model", "Create a custom process by combining multiple techniques.")
        ], "mode_combo")

    def _build_technique_section(self):
        return self._create_combo_group("Technique Selection", [
            ("LSB++", "Hides data in PNG pixels using an adaptive LSB algorithm."),
            ("Locomotive", "Fragments and appends data across multiple PNGs."),
            ("Metadata", "Hides messages within PNG text chunks or MP3 tags")
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
        if attribute_name == "mode_combo":
            combo.currentIndexChanged.connect(self.on_mode_changed)
        else:
            combo.currentIndexChanged.connect(self.on_technique_changed)
        layout.addWidget(combo)
        box.setLayout(layout)
        return box

    def _build_carrier_section(self):
        box = QGroupBox("Carrier Input")
        box.setMinimumHeight(75)
        box.setMaximumHeight(90)
        layout = QGridLayout()
        layout.setContentsMargins(6, 12, 6, 6)
        layout.setSpacing(6)
        self.carrier_edit = QLineEdit()
        self.carrier_edit.setReadOnly(True)
        self.carrier_edit.setPlaceholderText("Select PNG Image...")
        self.carrier_browse_btn = QPushButton("Browse")
        layout.addWidget(self.carrier_edit, 0, 0)
        layout.addWidget(self.carrier_browse_btn, 0, 1)
        box.setLayout(layout)
        return box

    def _build_payload_section(self):
        box = QGroupBox("Payload Input")
        box.setMinimumHeight(200)
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 12, 6, 6)
        layout.setSpacing(4)
        
        self.payload_stack = QStackedWidget()
        self.payload_stack.addWidget(self._create_standard_payload_page())
        
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
        
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        btn_editor = QPushButton("Text Editor")
        btn_editor.setMinimumSize(100, 25)
        btn_editor.setStyleSheet("font-size: 8pt; padding: 2px;")
        btn_editor.clicked.connect(self.open_text_editor)
        
        self.lbl_capacity = QLabel("capacity: 0/100")
        self.lbl_capacity.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_capacity.setStyleSheet("color: #aaa; font-size: 8pt;")
        
        toolbar.addWidget(btn_editor)
        toolbar.addStretch()
        toolbar.addWidget(self.lbl_capacity)
        
        self.payload_text = QTextEdit()
        self.payload_text.setPlaceholderText("Enter secret message here...")
        
        layout.addWidget(self.payload_text, 1)
        layout.addLayout(toolbar, 0)
        
        self.payload_text.textChanged.connect(self.update_capacity_indicator)
        self.payload_text.textChanged.connect(self._on_payload_changed)
        
        return tab

    def _create_file_payload_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        
        self.payload_file_path = QLineEdit()
        self.payload_file_path.setPlaceholderText("Path to secret file...")
        self.payload_file_path.hide()
        
        self.attachment_widget = AttachmentDropWidget()
        self.attachment_widget.fileSelected.connect(self._on_file_selected)
        self.attachment_widget.fileCleared.connect(self.payload_file_path.clear)
        self.attachment_widget.requestBrowse.connect(self.browse_payload_file)

        layout.addWidget(self.attachment_widget, 1)
        layout.addWidget(self.payload_file_path, 0)
        
        return tab

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

    def _create_public_key_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        self.public_key_edit = QLineEdit()
        self.public_key_edit.setPlaceholderText("Path to public key...")
        self.public_key_edit.hide()
        layout.addWidget(self.public_key_edit) 

        self.pubkey_attachment = AttachmentDropWidget()
        self.pubkey_attachment.requestBrowse.connect(self.browse_public_key)
        self.pubkey_attachment.fileSelected.connect(self._on_public_key_selected)

        layout.addWidget(self.pubkey_attachment)

        return page

    def _add_visibility_toggle(self, line_edit):
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarNormalButton)
        action = line_edit.addAction(icon, QLineEdit.ActionPosition.TrailingPosition)
        
        def toggle():
            is_password = line_edit.echoMode() == QLineEdit.EchoMode.Password
            line_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if is_password else QLineEdit.EchoMode.Password
            )
        action.triggered.connect(toggle)

    def _toggle_encryption_inputs(self):
        self.enc_stack.setCurrentIndex(self.enc_combo.currentIndex())

    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def browse_single_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Carrier Image", "", "PNG Images (*.png)"
        )
        if file_path:
            self.current_image_path = file_path
            self.carrier_edit.setText(file_path)
            self._load_image_preview(file_path)
            self._update_stats(file_path, len(self.payload_text.toPlainText().encode()))
            self._reset_embed_ui()

    def _load_image_preview(self, image_path):
        pixmap = QPixmap(image_path)
        
        if not pixmap.isNull():
            self.original_preview_pixmaps['std'] = pixmap
            self._update_preview_scaling()
            self._update_file_metadata_label(image_path)
        else:
            self.preview_label_std.setText("Failed to load image")
            self.preview_info_label_std.hide()

    def _update_preview_scaling(self):
        if 'std' in self.original_preview_pixmaps and self.preview_label_std:
            pixmap = self.original_preview_pixmaps['std']
            label_width = self.preview_label_std.width()
            if label_width <= 0:
                label_width = 300
            max_height = min(280, int(self.height() * 0.4))
            if max_height < 150:
                max_height = 150
            
            scaled_pixmap = pixmap.scaled(
                label_width, max_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.preview_label_std.setPixmap(scaled_pixmap)
            self.preview_label_std.setText("")
            self.preview_label_std.setStyleSheet(
                "border: 1px solid #3daee9; background-color: #222; border-radius: 3px;"
            )

    def _update_file_metadata_label(self, file_path):
        try:
            filename = os.path.basename(file_path)
            # Show only filename (size is now in stats)
            info_text = filename
            
            self.preview_info_label_std.setText(info_text)
            self.preview_info_label_std.show()
        except OSError:
            self.preview_info_label_std.hide()

    def _on_payload_changed(self):
        """Update stats when payload changes"""
        if self.current_image_path:
            payload_size = len(self.payload_text.toPlainText().encode())
            self._update_stats(self.current_image_path, payload_size)

    def update_capacity_indicator(self):
        text = self.payload_text.toPlainText()
        count = len(text)
        max_cap = 100
        
        self.lbl_capacity.setText(f"capacity: {count}/{max_cap}")
        
        if count > max_cap:
            self.lbl_capacity.setStyleSheet("color: #ff5555; font-weight: bold; font-size: 8pt;")
        else:
            self.lbl_capacity.setStyleSheet("color: #aaa; font-size: 8pt;")

    def open_text_editor(self):
        current_text = self.payload_text.toPlainText()
        dialog = TextEditorDialog(current_text, self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.payload_text.setPlainText(dialog.get_text())

    def browse_payload_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Secret Text File", "", "Text Files (*.txt)"
        )
        
        if file_path:
            if hasattr(self, 'attachment_widget'):
                self.attachment_widget.set_file(file_path)
            
            self.payload_file_path.setText(file_path)
            
            if file_path.lower().endswith(".txt"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self.payload_text.setPlainText(content)
                    self.payload_tabs.setCurrentIndex(TAB_INDEX_TEXT)
                    self.update_capacity_indicator()
                except Exception as e:
                    print(f"Error reading text file: {e}")

    def _on_file_selected(self, file_path):
        self.payload_file_path.setText(file_path)
        
        if file_path.lower().endswith(".txt"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.payload_text.setPlainText(content)
                self.payload_tabs.setCurrentIndex(TAB_INDEX_TEXT)
                self.update_capacity_indicator()
            except Exception as e:
                print(f"Error reading text file: {e}")

    def _on_public_key_selected(self, file_path):
        self.public_key_edit.setText(file_path)

    def browse_public_key(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Public Key", "", "PEM Files (*.pem);;All Files (*)"
        )
        if file_path:
            self.public_key_edit.setText(file_path)
            if hasattr(self, 'pubkey_attachment'):
                try:
                    self.pubkey_attachment.set_file(file_path)
                except Exception:
                    pass

    def on_mode_changed(self):
        is_configurable = "Configurable" in self.mode_combo.currentText()
        
        if is_configurable:
            self.right_panel_stack.setCurrentIndex(PAGE_CONFIGURABLE)
        else:
            self.on_technique_changed()

    def on_technique_changed(self):
        current_tech = self.tech_combo.currentText()
        is_locomotive = "Locomotive" in current_tech
        
        disconnect_signal_safely(self.carrier_browse_btn.clicked)

        if is_locomotive:
            self.right_panel_stack.setCurrentIndex(PAGE_LOCOMOTIVE)
        else:
            self.right_panel_stack.setCurrentIndex(PAGE_STANDALONE)
            self.carrier_browse_btn.clicked.connect(self.browse_single_image)

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        if self.original_preview_pixmaps:
            self._update_preview_scaling()


# ============================================================================
# STANDALONE TEST RUNNER
# ============================================================================

def main():
    """Standalone test runner for the redesigned Embed Tab"""
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLE)
    
    window = QMainWindow()
    window.setWindowTitle("Embed Tab Prototype")
    window.setGeometry(100, 100, 1200, 700)
    
    embed_tab = EmbedTab()
    window.setCentralWidget(embed_tab)
    
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
