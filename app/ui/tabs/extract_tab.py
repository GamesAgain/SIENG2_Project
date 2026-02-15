# PYQT6 FRAMEWORK (GUI)
import os
from tkinter import Image
from PyQt6.QtCore import (
    Qt, QTimer, QSize, pyqtSignal
)

from PyQt6.QtGui import (
    QPixmap, QFont, QDragEnterEvent, QDropEvent, QResizeEvent, QIcon, QPainter, QColor, QPen
)
from PyQt6.QtCore import QMimeData
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

from app.ui.tabs.embed_tab import DraggablePreviewLabel
from app.utils.file_io import format_file_size


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

from app.ui.components.attachment_drop_widget import AttachmentDropWidget
from app.ui.components.metadata_drop_widget import MetadataDropWidget
from app.ui.dialogs.text_editor_dialog import TextEditorDialog

class ExtractTab(QWidget):
    def __init__(self):
       super().__init__()
       self.init_ui()
       
    def init_ui(self):
        self.setMinimumSize(1000, 700)
        
        
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)
        
        left_panel = self.create_left_panel()
        right_panel = self.create_right_panel()
        
        #ratio: left panel gets 35%, right panel gets 65%
        main_layout.addWidget(left_panel, 35)
        main_layout.addWidget(right_panel, 65)
        
        # self.on_technique_changed()
        
    def create_left_panel(self):
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
        
        layout.addWidget(self.build_mode_section())
        layout.addWidget(self.build_technique_section())
        layout.addWidget(self.build_stego_section())
        layout.addWidget(self.build_preview_section())
        layout.addWidget(self.build_decryption_section())
        layout.addStretch()
        
        scroll_area.setWidget(widget)
        return scroll_area
    
    def build_mode_section(self):
        return self.create_combo_group("Mode Selection", [
            (
                "Standalone", 
                "Hide data using one specific method independently."
            ),
            (
                "Configurable Model", 
                "Create a custom process by combining multiple techniques."
            )
        ], "mode_combo")

    def build_technique_section(self):
        return self.create_combo_group("Technique Selection", [
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
    
    def create_combo_group(self, title, items, attribute_name):
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
        # combo.currentIndexChanged.connect(self.on_technique_changed)
        
        # if attribute_name == "mode_combo":
        #     combo.currentIndexChanged.connect(self.on_mode_changed)
        # else:
        #     combo.currentIndexChanged.connect(self.on_technique_changed)


        layout.addWidget(combo)
        box.setLayout(layout)
        return box
    def build_stego_section(self):
            box = QGroupBox("Select Stego File")
            box.setMinimumHeight(75)
            box.setMaximumHeight(90)
            
            layout = QHBoxLayout() 
            layout.setContentsMargins(6, 12, 6, 6)
            layout.setSpacing(6)
            
            self.stegoFile_edit = QLineEdit()
            self.stegoFile_edit.setReadOnly(True)
            self.stegoFile_edit.setPlaceholderText("Select PNG Image...")
            
            self.stegoFile_browse_btn = QPushButton("Browse")
            
            layout.addWidget(self.stegoFile_edit)
            layout.addWidget(self.stegoFile_browse_btn)
            
            box.setLayout(layout)
            return box
    
    def build_preview_section(self):
        stack = self.create_preview_area()
        self.preview_stack = stack
        
        return stack
        
        
    def create_preview_area(self):
        stack = QStackedWidget()
        stack.addWidget(self.create_lsb_page())
        # stack.addWidget(self.create_locomotive_page())
        # stack.addWidget(self.create_metadata_page())
        return stack
        
    def create_lsb_page(self):
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
        
        
        # self.preview_label.image_dropped.connect(self._on_preview_image_dropped)
        
        group_layout.addWidget(self.preview_label, 1)
        
        # Info Label (file info)
        preview_info_label = QLabel("")
        preview_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_info_label.setStyleSheet("color: #e0e0e0; font-size: 9pt;")
        preview_info_label.hide()
        setattr(self, f"preview_info_label", preview_info_label)
        
        group_layout.addWidget(preview_info_label, 0)
        
        
        # Stats Row (below preview)
        stats_container = self.build_stats_row()
        group_layout.addWidget(stats_container, 0)
        
        group_box.setLayout(group_layout)
        return group_box
    
    def build_stats_row(self):
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
        self.stat_filename = self.create_stat_item("File:", "No Image", "#e0e0e0")
        layout.addWidget(self.stat_filename)
        
        # Image Size Stat
        self.stat_image_size = self.create_stat_item("Image Size:", "No Image", "#e0e0e0")
        layout.addWidget(self.stat_image_size)
         
        return container
    
    def create_stat_item(self, label_text, value_text, color):
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
    
    def build_decryption_section(self):
        self.encryption_box = QGroupBox("Decryption Options")
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
        self.enc_combo.addItem("Private Key (RSA-3072)", "private")
        self.enc_combo.setItemData(0, "Use a passphrase to encrypt the payload", tt)
        self.enc_combo.setItemData(1, "Use RSA public key to encrypt the payload", tt)
        
        self.enc_combo.currentIndexChanged.connect(self.toggle_decryption_inputs)
        type_row.addWidget(self.lbl_key)
        type_row.addWidget(self.enc_combo)
        layout.addLayout(type_row)

        self.enc_stack = QStackedWidget()
        self.enc_stack.addWidget(self.create_password_page())
        self.enc_stack.addWidget(self.create_private_key_page())
        
        layout.addWidget(self.enc_stack)
        self.encryption_box.setLayout(layout)
        
        self.encryption_box.toggled.connect(self.enc_combo.setEnabled)
        self.encryption_box.toggled.connect(self.enc_stack.setEnabled)
        
        return self.encryption_box
    
    def toggle_decryption_inputs(self):
        self.enc_stack.setCurrentIndex(self.enc_combo.currentIndex())
        
    def create_password_page(self):
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_pass = QLabel("Password:")
        self.passphrase = QLineEdit()
        self.passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.passphrase.setPlaceholderText("Enter Passphrase...")
        self.add_visibility_toggle(self.passphrase)
        
        self.lbl_confirm = QLabel("Confirm:")
        self.confirmpassphrase = QLineEdit()
        self.confirmpassphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirmpassphrase.setPlaceholderText("Confirm Passphrase...")
        self.add_visibility_toggle(self.confirmpassphrase)

        layout.addWidget(self.lbl_pass, 0, 0)
        layout.addWidget(self.passphrase, 0, 1)
        layout.addWidget(self.lbl_confirm, 1, 0)
        layout.addWidget(self.confirmpassphrase, 1, 1)
        
        return page
    
    def add_visibility_toggle(self, line_edit):
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
        
        
    def create_private_key_page(self):
        page = QWidget()
        layout = QVBoxLayout(page) 
        layout.setContentsMargins(0, 0, 0, 0)

        self.private_key_edit = QLineEdit()
        self.private_key_edit.setPlaceholderText("Path to public key...")
        self.private_key_edit.hide()
        layout.addWidget(self.private_key_edit) 

        # Attachment widget for public key (accept .pem by default)
        self.prikey_attachment = AttachmentDropWidget(allowed_extensions='.pem')
        
        try:
            self.prikey_attachment.empty_label.setText("Import Private Key\n(.pem files)")
        except Exception:
            pass

        # self.pubkey_attachment.requestBrowse.connect(self.browse_public_key)
        # self.pubkey_attachment.fileSelected.connect(self.on_public_key_selected)

        layout.addWidget(self.prikey_attachment)

        return page
    
    def create_right_panel(self):
        box = QGroupBox("Payload Input")
        self.payload_main_group = box
        box.setMinimumHeight(200)
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 12, 6, 6)
        layout.setSpacing(4)
        
        self.payload_stack = QStackedWidget()
        self.payload_stack.addWidget(self.create_standard_payload_page())
        # self.payload_stack.addWidget(self._create_metadata_preview_page())
        
        size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        size_policy.setVerticalStretch(1)
        self.payload_stack.setSizePolicy(size_policy)
        
        layout.addWidget(self.payload_stack, 1)
        layout.addWidget(self.build_execution_group("Extract data", "loco"), 0)
        box.setLayout(layout)
        return box
    
    def build_execution_group(self, button_text, prefix):
        container = QWidget()
        container.setMinimumHeight(60)
        container.setMaximumHeight(80)
        
        
        # เก็บ container เพื่อให้สามารถซ่อน/แสดงได้ในภายหลัง
        setattr(self, f"{prefix}_execution_container", container)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        
        # สร้างปุ่มและตั้งชื่อตัวแปรแบบ Dynamic ตาม prefix
        btn_exec = QPushButton(button_text)
        btn_exec.setMinimumHeight(35)
        btn_exec.setStyleSheet(
            "font-weight: bold; font-size: 11pt; "
            "background-color: #2d5a75; border-radius: 4px; color: white;"
        )
        setattr(self, f"{prefix}_btn_exec", btn_exec)
        
        # Progress Bar
        progress_bar = QProgressBar()
        progress_bar.setValue(0)
        progress_bar.setTextVisible(False)
        progress_bar.setFixedHeight(6)
        setattr(self, f"{prefix}_progress_bar", progress_bar)
        
        # Status Label
        status_label = QLabel("Ready.")
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_label.setStyleSheet("color: #888; font-size: 9pt;")
        setattr(self, f"{prefix}_status_label", status_label)
        
        # Connect Signal
        # btn_exec.clicked.connect(lambda: self.on_run_embed())
        
        # Layout
        hlayout = QHBoxLayout() 
        hlayout.setSpacing(10)
        hlayout.addWidget(btn_exec)
        
        layout.addLayout(hlayout)
        layout.addWidget(progress_bar)
        layout.addWidget(status_label)
        
        
        return container
    
    def create_standard_payload_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.payload_tabs = QTabWidget()
        self.payload_tabs.addTab(self.create_text_payload_tab(), "Text Message")
        self.payload_tabs.addTab(self.create_file_payload_tab(), "File Attachment")
        
        layout.addWidget(self.payload_tabs)
        return page
    
    def create_text_payload_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(4)
            
            self.payload_text = QTextEdit()
            self.payload_text.setPlaceholderText("Enter secret message here...")
            
            # toolbar: text editor & capacity text
            toolbar = QHBoxLayout()
            toolbar.setSpacing(4)
            btn_editor = QPushButton("Save as txt.")
            btn_editor.setMinimumSize(100, 25)
            btn_editor.setStyleSheet("font-size: 8pt; padding: 2px;")
            
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
        
    def update_capacity_indicator(self):
        """คำนวณขนาดและแสดงสถานะ 3 ระดับ"""
        if not hasattr(self, 'payload_text'): return

        text_bytes = self.payload_text.toPlainText().encode('utf-8')
        current_size = len(text_bytes)
            
        self.lbl_capacity.setText(f"Size: {format_file_size(current_size)}")
            
    
    def create_file_payload_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 10, 5, 10)  # Balanced top/bottom spacing
        layout.setSpacing(6)
        
        self.payload_file_path = QLineEdit()
        self.payload_file_path.setPlaceholderText("Path to secret file...")
        self.payload_file_path.hide()
        
        self.attachment_widget = AttachmentDropWidget()
        # self.attachment_widget.fileSelected.connect(self.on_file_attach_selected)
        self.attachment_widget.fileCleared.connect(self.payload_file_path.clear)

        # self.attachment_widget.requestBrowse.connect(self.browse_payload_file)

        # Default hint: prefer text-mode files for File Attachment techniques
        try:
            self.attachment_widget.empty_label.setText("Drag & Drop\n(Text files only: .txt, .md, .csv, ...)")
        except Exception:
            pass

        layout.addWidget(self.attachment_widget, 1)
        layout.addWidget(self.payload_file_path, 0)
        
        return tab
       
    
        
    