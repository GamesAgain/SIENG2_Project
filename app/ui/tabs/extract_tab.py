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

class EmbedTab(QWidget):
    def __init__(self):
       super().__init__()
       self._init_ui()
       
    def _init_ui(self):
        self.setMinimumSize(800, 500)
        
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)
        
        left_panel = self._create_left_panel()
        self.right_panel_stack = self._create_right_panel()
        
        #ratio: left panel gets 35%, right panel gets 65%
        main_layout.addWidget(left_panel, 35)
        main_layout.addWidget(self.right_panel_stack, 65)
        
        # self.on_technique_changed()
        
    def _create_left_panel(self):
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
        stack = QStackedWidget()
        # stack.addWidget(self._create_standalone_page())
        # stack.addWidget(self._create_locomotive_page())
        # stack.addWidget(self._create_configurable_page())
        return stack
    
    # Components(Groupbox) of left panel
    def _build_mode_section(self):
        return self._create_combo_group("Mode Selection", [
            (
                "Standalone", 
                "Hide data using one specific method independently."
            ),
            (
                "Configurable Model", 
                "Create a custom process by combining multiple techniques."
            )
        ], "mode_combo")

    def _build_technique_section(self):
        return self._create_combo_group("Technique Selection", [
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
        # Connect to appropriate handler based on attribute name
        # if attribute_name == "mode_combo":
        #     combo.currentIndexChanged.connect(self.on_mode_changed)
        # else:
        #     combo.currentIndexChanged.connect(self.on_technique_changed)
        layout.addWidget(combo)
        box.setLayout(layout)
        return box
        
    def _build_carrier_section(self):
            box = QGroupBox("Carrier Input")
            box.setMinimumHeight(75)
            box.setMaximumHeight(90)
            
            layout = QHBoxLayout() 
            layout.setContentsMargins(6, 12, 6, 6)
            layout.setSpacing(6)
            
            self.carrier_edit = QLineEdit()
            self.carrier_edit.setReadOnly(True)
            self.carrier_edit.setPlaceholderText("Select PNG Image...")
            
            self.carrier_browse_btn = QPushButton("Browse")
            
            layout.addWidget(self.carrier_edit)
            layout.addWidget(self.carrier_browse_btn)
            
            box.setLayout(layout)
            return box
    
    def _build_payload_section(self):
        box = QGroupBox("Payload Input")
        self.payload_main_group = box
        box.setMinimumHeight(200)
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 12, 6, 6)
        layout.setSpacing(4)
        
        self.payload_stack = QStackedWidget()
        self.payload_stack.addWidget(self._create_standard_payload_page())
        # self.payload_stack.addWidget(self._create_metadata_payload_page())
        
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
            
            self.payload_text = QTextEdit()
            self.payload_text.setPlaceholderText("Enter secret message here...")
            
            # toolbar: text editor & capacity text
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
        
            layout.addWidget(self.payload_text, 1)
            layout.addLayout(toolbar, 0)
            
            self.payload_text.textChanged.connect(self.update_capacity_indicator)
            
            # self.payload_text.textChanged.connect(self._on_payload_changed)
            
            return tab
    
    def _create_file_payload_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 10, 5, 10)  # Balanced top/bottom spacing
        layout.setSpacing(6)
        
        self.payload_file_path = QLineEdit()
        self.payload_file_path.setPlaceholderText("Path to secret file...")
        self.payload_file_path.hide()
        
        self.attachment_widget = AttachmentDropWidget()
        self.attachment_widget.fileSelected.connect(self._on_file_selected)
        self.attachment_widget.fileCleared.connect(self.payload_file_path.clear)

        self.attachment_widget.requestBrowse.connect(self.browse_payload_file)

        # Default hint: prefer text-mode files for File Attachment techniques
        try:
            self.attachment_widget.empty_label.setText("Drag & Drop\n(Text files only: .txt, .md, .csv, ...)")
        except Exception:
            pass

        layout.addWidget(self.attachment_widget, 1)
        layout.addWidget(self.payload_file_path, 0)
        
        return tab
                    
    # ========================================================================
    # CAPACITY & TEXT EDITOR
    # ========================================================================

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
            
    # ========================================================================
    # FILE SELECTION HANDLERS
    # ========================================================================
    
    def _on_file_selected(self, file_path):
        """Handle file selection from drag-drop (called by signal from AttachmentDropWidget)"""
        # NOTE: This is ONLY called when user drags a file, NOT when browsing
        
        self.payload_file_path.setText(file_path)
        
        current_tech = self.tech_combo.currentText()
        is_locomotive = "Locomotive" in current_tech
        
        # Extract text content for LSB++ mode
        if not is_locomotive:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in TEXT_FILE_EXTENSIONS:
                try:
                    # Simple read with UTF-8
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self.payload_text.setPlainText(content)
                    self.payload_tabs.setCurrentIndex(TAB_INDEX_TEXT)
                    self.update_capacity_indicator()
                except UnicodeDecodeError:
                    # Try other common encodings
                    for encoding in ['utf-16', 'latin-1', 'cp1252']:
                        try:
                            with open(file_path, 'r', encoding=encoding) as f:
                                content = f.read()
                            self.payload_text.setPlainText(content)
                            self.payload_tabs.setCurrentIndex(TAB_INDEX_TEXT)
                            self.update_capacity_indicator()
                            break
                        except:
                            continue
                except Exception as e:
                    print(f"Error reading file: {e}")

    def _on_public_key_selected(self, file_path):
        """Handler for when a public-key file is selected in the attachment widget."""
        self.public_key_edit.setText(file_path)

    def browse_public_key(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Public Key", "", "PEM Files (*.pem);;All Files (*)"
        )
        if file_path:
            # Update both the read-only path field and the attachment widget
            self.public_key_edit.setText(file_path)
            if hasattr(self, 'pubkey_attachment'):
                try:
                    self.pubkey_attachment.set_file(file_path)
                except Exception:
                    pass
    
    def browse_payload_file(self):
        current_tech = self.tech_combo.currentText()
        is_locomotive = "Locomotive" in current_tech

        if is_locomotive:
            file_filter = "All Files (*)"
            caption = "Select Secret File (Any Type)"
        else:
            # Expanded file filters for LSB++ mode
            file_filter = (
                "Text Files (*.txt *.md *.csv *.json *.xml *.log);;"
                "Code Files (*.py *.js *.ts *.java *.cpp *.c *.h *.cs *.go *.rs);;"
                "Config Files (*.yml *.yaml *.toml *.ini *.conf *.cfg *.env);;"
                "Web Files (*.html *.css *.scss *.jsx *.tsx *.vue);;"
                "Script Files (*.sql *.sh *.bat *.ps1);;"
                "All Files (*)"
            )
            caption = "Select Secret Text File"

        file_path, _ = QFileDialog.getOpenFileName(self, caption, "", file_filter)
        
        if file_path:
            # Set file in attachment widget (this is the ONLY place we call set_file from browse)
            if hasattr(self, 'attachment_widget'):
                self.attachment_widget.set_file(file_path)
            
            self.payload_file_path.setText(file_path)
            
            # Extract text content for LSB++ mode
            if not is_locomotive:
                ext = os.path.splitext(file_path)[1].lower()
                if ext in TEXT_FILE_EXTENSIONS:
                    try:
                        # Simple read with UTF-8
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        self.payload_text.setPlainText(content)
                        self.payload_tabs.setCurrentIndex(TAB_INDEX_TEXT)
                        self.update_capacity_indicator()
                    except UnicodeDecodeError:
                        # Try other common encodings
                        for encoding in ['utf-16', 'latin-1', 'cp1252']:
                            try:
                                with open(file_path, 'r', encoding=encoding) as f:
                                    content = f.read()
                                self.payload_text.setPlainText(content)
                                self.payload_tabs.setCurrentIndex(TAB_INDEX_TEXT)
                                self.update_capacity_indicator()
                                break
                            except:
                                continue
                    except Exception as e:
                        print(f"Error reading file: {e}")
                        
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
    
    def _toggle_encryption_inputs(self):
        self.enc_stack.setCurrentIndex(self.enc_combo.currentIndex())
        
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
    
    def _add_visibility_toggle(self, line_edit):
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
    
    def _create_public_key_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)  # เปลี่ยนเป็น QVBoxLayout เพื่อจัดวางง่ายขึ้น
        layout.setContentsMargins(0, 0, 0, 0)

        self.public_key_edit = QLineEdit()
        self.public_key_edit.setPlaceholderText("Path to public key...")
        self.public_key_edit.hide()
        layout.addWidget(self.public_key_edit) 

        # Attachment widget for public key (accept .pem by default)
        self.pubkey_attachment = AttachmentDropWidget()
        
        try:
            self.pubkey_attachment.empty_label.setText("Import Public Key\n(.pem files)")
        except Exception:
            pass

        # เชื่อม Signal
        self.pubkey_attachment.requestBrowse.connect(self.browse_public_key)
        self.pubkey_attachment.fileSelected.connect(self._on_public_key_selected)

        layout.addWidget(self.pubkey_attachment)

        return page
        
    