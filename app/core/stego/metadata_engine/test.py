import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QTabWidget, QFormLayout, QLineEdit, QTextEdit, QMessageBox)
from PIL import Image
import piexif
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TYER, COMM

class MetadataEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pro Metadata Editor (JPEG, PNG, MP3)")
        self.resize(600, 500)
        self.current_file = None
        
        # Main Layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()
        main_widget.setLayout(layout)

        # File Selection
        btn_layout = QHBoxLayout()
        self.btn_open = QPushButton("Open File")
        self.btn_open.clicked.connect(self.open_file)
        self.lbl_filename = QLabel("No file selected")
        btn_layout.addWidget(self.btn_open)
        btn_layout.addWidget(self.lbl_filename)
        layout.addLayout(btn_layout)

        # Tabs
        self.tabs = QTabWidget()
        self.tab1 = QWidget() # General (Windows Style)
        self.tab2 = QWidget() # Custom (Advanced/Raw)
        
        self.tabs.addTab(self.tab1, "General (Windows Detail)")
        self.tabs.addTab(self.tab2, "Custom / Advanced Tags")
        layout.addWidget(self.tabs)

        # Init Tab Layouts
        self.init_tab1_ui()
        self.init_tab2_ui()

        # Save Button
        self.btn_save = QPushButton("Save Metadata")
        self.btn_save.clicked.connect(self.save_metadata)
        layout.addWidget(self.btn_save)

    def init_tab1_ui(self):
        """Layout for Tab 1: Common Fields"""
        self.form_layout_1 = QFormLayout()
        self.tab1.setLayout(self.form_layout_1)
        
        # Fields placeholders (Will be populated dynamically)
        self.input_title = QLineEdit()
        self.input_artist = QLineEdit() # Or Author
        self.input_album = QLineEdit()  # Or Subject
        self.input_comment = QTextEdit()
        self.input_comment.setMaximumHeight(60)

        self.form_layout_1.addRow("Title:", self.input_title)
        self.form_layout_1.addRow("Artist/Author:", self.input_artist)
        self.form_layout_1.addRow("Album/Subject:", self.input_album)
        self.form_layout_1.addRow("Comments:", self.input_comment)

    def init_tab2_ui(self):
        """Layout for Tab 2: Specific/Raw Data"""
        layout = QVBoxLayout()
        self.tab2.setLayout(layout)
        self.lbl_custom_info = QLabel("Custom data will appear here based on file type.")
        self.txt_custom_data = QTextEdit() # To show raw data like XML or iTXt
        layout.addWidget(self.lbl_custom_info)
        layout.addWidget(self.txt_custom_data)

    def open_file(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Files (*.jpg *.jpeg *.png *.mp3)")
        if fname:
            self.current_file = fname
            self.lbl_filename.setText(os.path.basename(fname))
            self.load_metadata(fname)

    def load_metadata(self, fpath):
        ext = os.path.splitext(fpath)[1].lower()
        
        # Clear inputs
        self.input_title.clear()
        self.input_artist.clear()
        self.input_album.clear()
        self.input_comment.clear()
        self.txt_custom_data.clear()

        if ext in ['.jpg', '.jpeg']:
            self.load_jpeg(fpath)
        elif ext == '.png':
            self.load_png(fpath)
        elif ext == '.mp3':
            self.load_mp3(fpath)

    def load_jpeg(self, fpath):
        # Using Piexif for EXIF data
        try:
            exif_dict = piexif.load(fpath)
            # Example mapping (Simplify for demo)
            # Note: Windows specific tags (XPTitle) are in '0th' ifd with specific IDs
            self.lbl_custom_info.setText("Raw EXIF Data:")
            self.txt_custom_data.setText(str(exif_dict))
        except Exception as e:
            print(f"Error loading JPEG: {e}")

    def load_png(self, fpath):
        try:
            img = Image.open(fpath)
            info = img.info
            
            # Tab 1 Mapping
            self.input_title.setText(info.get('Title', ''))
            self.input_artist.setText(info.get('Author', ''))
            self.input_comment.setText(info.get('Description', ''))
            
            # Tab 2 (Custom - iTXt/tEXt)
            raw_text = "--- PNG Info Chunks ---\n"
            for k, v in info.items():
                raw_text += f"{k}: {v}\n"
            
            self.lbl_custom_info.setText("PNG Text Chunks (iTXt/tEXt/zTXt):")
            self.txt_custom_data.setText(raw_text)
        except Exception as e:
            print(f"Error loading PNG: {e}")

    def load_mp3(self, fpath):
        try:
            audio = MP3(fpath, ID3=ID3)
            
            # Tab 1 Mapping (ID3 Tags)
            if 'TIT2' in audio: self.input_title.setText(str(audio['TIT2']))
            if 'TPE1' in audio: self.input_artist.setText(str(audio['TPE1']))
            if 'TALB' in audio: self.input_album.setText(str(audio['TALB']))
            if 'COMM::eng' in audio: self.input_comment.setText(str(audio['COMM::eng']))
            
            # Tab 2
            self.lbl_custom_info.setText("Raw ID3 Tags:")
            self.txt_custom_data.setText(str(audio.pprint()))
        except Exception as e:
            print(f"Error loading MP3: {e}")

    def save_metadata(self):
        if not self.current_file: return
        QMessageBox.information(self, "Info", "Save functionality needs logic implementation for each library.")
        # Logic การบันทึกต้องเขียนแยกตาม Library (Piexif.dump, Mutagen.save, PngInfo)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MetadataEditor()
    window.show()
    sys.exit(app.exec())