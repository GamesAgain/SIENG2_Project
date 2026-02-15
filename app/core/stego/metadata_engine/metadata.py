import os
import json
import shutil
from PIL import Image, PngImagePlugin
import piexif
import piexif.helper
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TCOP, COMM, TDRC, TALB, TRCK, TCON, TCOM, TPOS, TSSE, TXXX, APIC, TIT3

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QFormLayout, 
    QLineEdit, QTextEdit, QPushButton, QLabel, QMessageBox, 
    QTableWidget, QTableWidgetItem, QHeaderView, QStackedWidget,
    QSpinBox, QFileDialog, QScrollArea, QGroupBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
DARK_STYLE = """
QMainWindow, QDialog, QAbstractItemView, QTabWidget::pane {
    background-color: #2b2b2b;
    color: #e0e0e0;
    font-family: 'Segoe UI', sans-serif;
    font-size: 10pt;
}

QGroupBox {
    border: 1px solid #555;
    border-radius: 5px;
    margin-top: 10px;
    font-weight: bold;
    color: #bbb;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
}

QLineEdit, QTextEdit, QListWidget, QComboBox {
    background-color: #3c3f41;
    border: 1px solid #555;
    border-radius: 4px;
    color: #fff;
    padding: 5px;
}

QComboBox QAbstractItemView {
    background-color: #3c3f41;
    color: #e0e0e0;
    border: 1px solid #555;
    selection-background-color: #2d5a75;
    selection-color: #fff;
    outline: 0px;
}

QPushButton {
    background-color: #3c3f41;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 6px 12px;
    color: #fff;
}
QPushButton:hover {
    background-color: #444;
    border: 1px solid #3daee9;
}

QTabBar::tab {
    background: #1e1e1e;
    color: #777;
    padding: 8px 20px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
    border: 1px solid #333;
}
QTabBar::tab:selected {
    background: #444444;
    color: #fff;
    border-top: 2px solid #3daee9;
    border-bottom: 1px solid #444444;
    font-weight: bold;
}
QTabBar::tab:!selected:hover {
    background: #333;
    color: #bbb;
}

QProgressBar {
    border: 1px solid #555;
    border-radius: 4px;
    text-align: center;
    background-color: #3c3f41;
    height: 8px;
}
QProgressBar::chunk {
    background-color: #3daee9;
    width: 20px;
}
QScrollArea, QScrollArea > QWidget > QWidget {
    border: none;
    background-color: transparent; 
}

QScrollBar:vertical {
    width: 10px;
    margin: 0px 0px 0px 0px;
}
QScrollBar::handle:vertical {
    background: #555;
    min-height: 20px;
    border-radius: 5px;
}

QSplitter::handle {
    background-color: #444;
    height: 2px;
}
"""

# ==========================================
# 1. ENHANCED BACKEND LOGIC
# ==========================================
class MetadataHandler:
    @staticmethod
    def get_file_type(filepath):
        ext = os.path.splitext(filepath)[1].lower()
        if ext in ['.jpg', '.jpeg']:
            return 'JPEG'
        if ext == '.png':
            return 'PNG'
        if ext == '.mp3':
            return 'MP3'
        return None

    @staticmethod
    def str_to_rational(s):
        try:
            if '/' in s:
                n, d = map(int, s.split('/'))
                return (n, d)
            val = float(s)
            return (int(val * 100), 100)
        except:
            return (0, 1)

    @staticmethod
    def _decode_bytes(b_data):
        if not b_data:
            return ""
        if b_data.startswith(b'UNICODE\x00'):
            try:
                return b_data[8:].decode('utf-16').rstrip('\x00')
            except:
                pass
        elif b_data.startswith(b'ASCII\x00\x00\x00'):
            try:
                return b_data[8:].decode('utf-8').rstrip('\x00')
            except:
                pass
            
        decoders = ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'cp1252']
        for enc in decoders:
            try:
                val = b_data.decode(enc).rstrip('\x00')
                if val.strip().startswith('{') and val.strip().endswith('}'):
                    return val
                if enc == 'utf-8':
                    return val
            except:
                continue
        try:
            return b_data.decode('utf-8', errors='ignore')
        except:
            return str(b_data)

    @staticmethod
    def read_metadata(filepath):
        ftype = MetadataHandler.get_file_type(filepath)
        data = {
            "type": ftype,
            "description": {},
            "origin": {},
            "image": {},
            "media": {},
            "audio": {},
            "custom": [],
            "cover_art": None
        }
        
        try:
            if ftype == 'JPEG':
                img = Image.open(filepath)
                try:
                    exif_dict = piexif.load(img.info.get('exif', b''))
                except:
                    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

                def g_s(d, k):
                    return MetadataHandler._decode_bytes(d.get(k, b''))
                
                # Description section
                data["description"] = {
                    "Title": g_s(exif_dict["0th"], piexif.ImageIFD.ImageDescription),
                    "Subject": "",
                    "Rating": "",
                    "Tags": "",
                    "Comments": ""
                }
                
                # Origin section
                data["origin"] = {
                    "Authors": g_s(exif_dict["0th"], piexif.ImageIFD.Artist),
                    "Date taken": g_s(exif_dict["0th"], piexif.ImageIFD.DateTime),
                    "Program name": g_s(exif_dict["0th"], piexif.ImageIFD.Software),
                    "Date acquired": "",
                    "Copyright": g_s(exif_dict["0th"], piexif.ImageIFD.Copyright)
                }
                
                # Image section
                def g_r(d, k):
                    v = d.get(k)
                    return f"{v[0]}/{v[1]}" if isinstance(v, tuple) and v[1] != 0 else str(v or "")

                width, height = img.size
                data["image"] = {
                    "Image ID": "",
                    "Dimensions": f"{width} x {height}",
                    "Width": f"{width} pixels",
                    "Height": f"{height} pixels",
                    "Horizontal resolution": "96 dpi",
                    "Vertical resolution": "96 dpi",
                    "Bit depth": str(img.mode),
                    "Camera Model": g_s(exif_dict["0th"], piexif.ImageIFD.Model),
                    "Camera Maker": g_s(exif_dict["0th"], piexif.ImageIFD.Make),
                    "ISO Speed": str(exif_dict["Exif"].get(piexif.ExifIFD.ISOSpeedRatings, "")),
                    "Shutter Speed": g_r(exif_dict["Exif"], piexif.ExifIFD.ExposureTime),
                    "F-Number": g_r(exif_dict["Exif"], piexif.ExifIFD.FNumber),
                    "Focal Length": g_r(exif_dict["Exif"], piexif.ExifIFD.FocalLength),
                    "GPS Latitude": str(exif_dict.get("GPS", {}).get(piexif.GPSIFD.GPSLatitude, "")),
                    "GPS Longitude": str(exif_dict.get("GPS", {}).get(piexif.GPSIFD.GPSLongitude, ""))
                }

                # Handle custom tags from UserComment
                raw_comm = exif_dict["Exif"].get(piexif.ExifIFD.UserComment, b'')
                comm_str = MetadataHandler._decode_bytes(raw_comm)
                if "custom_tags" in comm_str:
                    try:
                        start = comm_str.find('{')
                        end = comm_str.rfind('}') + 1
                        if start != -1 and end != -1:
                            js = json.loads(comm_str[start:end])
                            data["description"]["Comments"] = js.get("real_comment", "")
                            if "custom_tags" in js:
                                for k, v in js["custom_tags"].items():
                                    data["custom"].append((k, str(v)))
                        else:
                            data["description"]["Comments"] = comm_str
                    except:
                        data["description"]["Comments"] = comm_str
                else:
                    data["description"]["Comments"] = comm_str

            elif ftype == 'PNG':
                img = Image.open(filepath)
                info = img.info
                width, height = img.size
                
                # Description section
                data["description"] = {
                    "Title": info.get("Title", ""),
                    "Rating": "",
                    "Tags": "",
                    "Comments": info.get("Description", "") or info.get("Comment", "")
                }
                
                # Origin section
                data["origin"] = {
                    "Authors": info.get("Author", ""),
                    "Date taken": "",
                    "Program name": info.get("Software", ""),
                    "Date acquired": info.get("Creation Time", ""),
                    "Copyright": info.get("Copyright", "")
                }
                
                # Image section
                data["image"] = {
                    "Image ID": "",
                    "Dimensions": f"{width} x {height}",
                    "Width": f"{width} pixels",
                    "Height": f"{height} pixels",
                    "Horizontal resolution": f"{info.get('dpi', (96, 96))[0]} dpi" if 'dpi' in info else "96 dpi",
                    "Vertical resolution": f"{info.get('dpi', (96, 96))[1]} dpi" if 'dpi' in info else "96 dpi",
                    "Bit depth": str(img.mode),
                    "Gamma": str(info.get("gamma", ""))
                }
                
                # Custom tags (iTXt chunks)
                exclude = ["Title", "Author", "Copyright", "Software", "Creation Time", 
                          "Description", "Comment", "interlace", "gamma", "dpi", "exif", 
                          "icc_profile", "transparency", "aspect"]
                for k, v in info.items():
                    if k not in exclude:
                        data["custom"].append((k, str(v)))

            elif ftype == 'MP3':
                audio = ID3(filepath)
                mp3_info = MP3(filepath)
                
                def g_i(k):
                    return str(audio.get(k, ""))
                
                # Description section
                data["description"] = {
                    "Title": g_i("TIT2"),
                    "Subtitle": g_i("TIT3"),
                    "Rating": "",
                    "Comments": ""
                }
                
                comm = audio.get("COMM::eng") or audio.get("COMM")
                data["description"]["Comments"] = comm.text[0] if comm else ""
                
                # Media section
                data["media"] = {
                    "Contributing artists": g_i("TPE1"),
                    "Album artist": g_i("TPE2"),
                    "Album": g_i("TALB"),
                    "Year": g_i("TDRC"),
                    "#": g_i("TRCK"),
                    "Genre": g_i("TCON"),
                    "Length": f"{int(mp3_info.info.length // 60):02d}:{int(mp3_info.info.length % 60):02d}",
                    "Composer": g_i("TCOM"),
                    "Disc Number": g_i("TPOS")
                }
                
                # Audio section
                data["audio"] = {
                    "Bitrate": f"{mp3_info.info.bitrate // 1000}kbps",
                    "Channels": f"{mp3_info.info.channels} ({'stereo' if mp3_info.info.channels == 2 else 'mono'})",
                    "Audio sample rate": f"{mp3_info.info.sample_rate / 1000:.2f} kHz"
                }
                
                # Origin section
                data["origin"] = {
                    "Software": g_i("TSSE"),
                    "Copyright": g_i("TCOP")
                }
                
                # Cover art
                if audio.get("APIC:"):
                    data["cover_art"] = audio.get("APIC:").data
                
                # Custom tags (TXXX)
                for f in audio.getall("TXXX"):
                    data["custom"].append((f.desc, f.text[0]))
                    
        except Exception as e:
            print(f"Read Error: {e}")
        
        return data

    @staticmethod
    def save_metadata(filepath, data):
        ftype = MetadataHandler.get_file_type(filepath)
        try:
            if ftype == 'JPEG':
                img = Image.open(filepath)
                try:
                    exif_dict = piexif.load(img.info.get('exif', b''))
                except:
                    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

                def t_b(s):
                    return s.encode('utf-8') if s else b""
                
                # Description
                exif_dict["0th"][piexif.ImageIFD.ImageDescription] = t_b(data["description"]["Title"])
                
                # Origin
                exif_dict["0th"][piexif.ImageIFD.Artist] = t_b(data["origin"]["Authors"])
                exif_dict["0th"][piexif.ImageIFD.Copyright] = t_b(data["origin"]["Copyright"])
                exif_dict["0th"][piexif.ImageIFD.Software] = t_b(data["origin"]["Program name"])
                if data["origin"]["Date taken"]:
                    exif_dict["0th"][piexif.ImageIFD.DateTime] = t_b(data["origin"]["Date taken"])
                
                # Image - Camera
                if "Camera Model" in data["image"] and data["image"]["Camera Model"]:
                    exif_dict["0th"][piexif.ImageIFD.Model] = t_b(data["image"]["Camera Model"])
                if "Camera Maker" in data["image"] and data["image"]["Camera Maker"]:
                    exif_dict["0th"][piexif.ImageIFD.Make] = t_b(data["image"]["Camera Maker"])
                
                # Image - Camera settings
                if "ISO Speed" in data["image"] and data["image"]["ISO Speed"]:
                    try:
                        exif_dict["Exif"][piexif.ExifIFD.ISOSpeedRatings] = int(data["image"]["ISO Speed"])
                    except:
                        pass
                if "Shutter Speed" in data["image"] and data["image"]["Shutter Speed"]:
                    exif_dict["Exif"][piexif.ExifIFD.ExposureTime] = MetadataHandler.str_to_rational(data["image"]["Shutter Speed"])
                if "F-Number" in data["image"] and data["image"]["F-Number"]:
                    exif_dict["Exif"][piexif.ExifIFD.FNumber] = MetadataHandler.str_to_rational(data["image"]["F-Number"])
                if "Focal Length" in data["image"] and data["image"]["Focal Length"]:
                    exif_dict["Exif"][piexif.ExifIFD.FocalLength] = MetadataHandler.str_to_rational(data["image"]["Focal Length"])

                # Custom Tags + Comments
                custom_dict = {k: v for k, v in data["custom"]}
                if custom_dict or data["description"]["Comments"]:
                    payload = {
                        "real_comment": data["description"]["Comments"],
                        "custom_tags": custom_dict
                    }
                    json_str = json.dumps(payload, ensure_ascii=False)
                    header = b'UNICODE\x00'
                    body = json_str.encode('utf-16-le')
                    exif_dict["Exif"][piexif.ExifIFD.UserComment] = header + body
                else:
                    exif_dict["Exif"][piexif.ExifIFD.UserComment] = b''
                
                img.save(filepath, exif=piexif.dump(exif_dict))

            elif ftype == 'PNG':
                img = Image.open(filepath)
                meta = PngImagePlugin.PngInfo()
                
                # Description
                if data["description"]["Title"]:
                    meta.add_text("Title", data["description"]["Title"])
                if data["description"]["Comments"]:
                    meta.add_text("Description", data["description"]["Comments"])
                
                # Origin
                if data["origin"]["Authors"]:
                    meta.add_text("Author", data["origin"]["Authors"])
                if data["origin"]["Copyright"]:
                    meta.add_text("Copyright", data["origin"]["Copyright"])
                if data["origin"]["Program name"]:
                    meta.add_text("Software", data["origin"]["Program name"])
                if data["origin"]["Date acquired"]:
                    meta.add_text("Creation Time", data["origin"]["Date acquired"])
                
                # Custom tags (iTXt)
                for k, v in data["custom"]:
                    meta.add_text(k, v)
                
                img.save(filepath, pnginfo=meta)

            elif ftype == 'MP3':
                audio = ID3(filepath)
                
                # Description
                audio.add(TIT2(encoding=3, text=data["description"]["Title"]))
                audio.add(TIT3(encoding=3, text=data["description"]["Subtitle"]))
                audio.add(COMM(encoding=3, lang='eng', desc='', text=data["description"]["Comments"]))
                
                # Media
                audio.add(TPE1(encoding=3, text=data["media"]["Contributing artists"]))
                audio.add(TPE2(encoding=3, text=data["media"]["Album artist"]))
                audio.add(TALB(encoding=3, text=data["media"]["Album"]))
                audio.add(TDRC(encoding=3, text=data["media"]["Year"]))
                audio.add(TRCK(encoding=3, text=data["media"]["#"]))
                audio.add(TCON(encoding=3, text=data["media"]["Genre"]))
                audio.add(TCOM(encoding=3, text=data["media"]["Composer"]))
                audio.add(TPOS(encoding=3, text=data["media"]["Disc Number"]))
                
                # Origin
                audio.add(TSSE(encoding=3, text=data["origin"]["Software"]))
                audio.add(TCOP(encoding=3, text=data["origin"]["Copyright"]))
                
                # Cover art
                if "cover_art_data" in data:
                    audio.add(APIC(encoding=3, mime='image/jpeg', type=3, data=data["cover_art_data"]))
                
                # Custom tags
                audio.delall("TXXX")
                for k, v in data["custom"]:
                    audio.add(TXXX(encoding=3, desc=k, text=v))
                
                audio.save()
                
            return True, "Metadata saved successfully"
        except Exception as e:
            return False, str(e)


# ==========================================
# 2. ENHANCED FRONTEND WIDGET
# ==========================================
class MetadataEditorWidget(QWidget):
    """
    Advanced Metadata Editor Widget
    Supports JPEG, PNG, MP3 with Windows Properties-like interface
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = None
        self.pending_cover_art = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        
        
        # Main tabs
        self.tabs = QTabWidget()
        self.tab_standard = self.setup_standard_tab()
        self.tab_custom = self.setup_custom_tab()
        
        self.tabs.addTab(self.tab_standard, "Standard Tags")
        self.tabs.addTab(self.tab_custom, "Custom Tags")
        layout.addWidget(self.tabs)
        
        # Save button
        self.btn_save = QPushButton("Save File")
        self.btn_save.setMinimumHeight(45)
        self.btn_save.setStyleSheet(
            "font-weight: bold; font-size: 11pt; "
            "background-color: #2d5a75; border-radius: 4px; color: white;"
        )
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self.save_file)
        layout.addWidget(self.btn_save)

    def setup_standard_tab(self):
        """Standard properties tab with sections based on file type"""
        w = QWidget()
        main_layout = QVBoxLayout()
        
        # Stacked widget for different file types
        self.stack = QStackedWidget()
        self.stack.addWidget(self.create_no_file_widget())  # 0
        self.stack.addWidget(self.create_jpeg_widget())     # 1
        self.stack.addWidget(self.create_png_widget())      # 2
        self.stack.addWidget(self.create_mp3_widget())      # 3
        
        main_layout.addWidget(self.stack)
        w.setLayout(main_layout)
        return w

    def create_no_file_widget(self):
        """Placeholder when no file is selected"""
        w = QWidget()
        layout = QVBoxLayout()
        label = QLabel("No File Selected\n\nSelect file (JPG, PNG, MP3)  from left panel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("background-color: #2a2a2a; color: #aaa; border-radius: 4px;")
        layout.addWidget(label)
        w.setLayout(layout)
        return w

    def create_jpeg_widget(self):
        """JPEG metadata widget with Description, Origin, and Image sections"""
        w = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        content = QWidget()
        layout = QVBoxLayout()
        
        # Description group
        desc_group = QGroupBox("Description")
        desc_group.setStyleSheet("QGroupBox { font-weight: bold; color: #4a9eff; }")
        desc_layout = QFormLayout()
        
        self.jpeg_title = QLineEdit()
        self.jpeg_subject = QLineEdit()
        self.jpeg_rating = QSpinBox()
        self.jpeg_rating.setMaximum(5)
        self.jpeg_tags = QLineEdit()
        self.jpeg_comments = QTextEdit()
        self.jpeg_comments.setMaximumHeight(80)
        
        for widget in [self.jpeg_title, self.jpeg_subject, self.jpeg_tags]:
            widget.setStyleSheet("background-color: #252525; color: white; padding: 5px; border: 1px solid #555;")
        self.jpeg_comments.setStyleSheet("background-color: #252525; color: white; border: 1px solid #555;")
        
        desc_layout.addRow("Title:", self.jpeg_title)
        desc_layout.addRow("Subject:", self.jpeg_subject)
        desc_layout.addRow("Rating:", self.jpeg_rating)
        desc_layout.addRow("Tags:", self.jpeg_tags)
        desc_layout.addRow("Comments:", self.jpeg_comments)
        desc_group.setLayout(desc_layout)
        layout.addWidget(desc_group)
        
        # Origin group
        origin_group = QGroupBox("Origin")
        origin_group.setStyleSheet("QGroupBox { font-weight: bold; color: #4a9eff; }")
        origin_layout = QFormLayout()
        
        self.jpeg_authors = QLineEdit()
        self.jpeg_date_taken = QLineEdit()
        self.jpeg_program = QLineEdit()
        self.jpeg_date_acquired = QLineEdit()
        self.jpeg_copyright = QLineEdit()
        
        for widget in [self.jpeg_authors, self.jpeg_date_taken, self.jpeg_program, 
                      self.jpeg_date_acquired, self.jpeg_copyright]:
            widget.setStyleSheet("background-color: #252525; color: white; padding: 5px; border: 1px solid #555;")
        
        origin_layout.addRow("Authors:", self.jpeg_authors)
        origin_layout.addRow("Date taken:", self.jpeg_date_taken)
        origin_layout.addRow("Program name:", self.jpeg_program)
        origin_layout.addRow("Date acquired:", self.jpeg_date_acquired)
        origin_layout.addRow("Copyright:", self.jpeg_copyright)
        origin_group.setLayout(origin_layout)
        layout.addWidget(origin_group)
        
        # Image group
        image_group = QGroupBox("Image")
        image_group.setStyleSheet("QGroupBox { font-weight: bold; color: #4a9eff; }")
        image_layout = QFormLayout()
        
        self.jpeg_image_id = QLineEdit()
        self.jpeg_dimensions = QLineEdit()
        self.jpeg_dimensions.setReadOnly(True)
        self.jpeg_width = QLineEdit()
        self.jpeg_width.setReadOnly(True)
        self.jpeg_height = QLineEdit()
        self.jpeg_height.setReadOnly(True)
        self.jpeg_h_resolution = QLineEdit()
        self.jpeg_h_resolution.setReadOnly(True)
        self.jpeg_v_resolution = QLineEdit()
        self.jpeg_v_resolution.setReadOnly(True)
        self.jpeg_bit_depth = QLineEdit()
        self.jpeg_bit_depth.setReadOnly(True)
        self.jpeg_camera_model = QLineEdit()
        self.jpeg_camera_maker = QLineEdit()
        self.jpeg_iso = QLineEdit()
        self.jpeg_shutter = QLineEdit()
        self.jpeg_fnumber = QLineEdit()
        self.jpeg_focal = QLineEdit()
        self.jpeg_gps_lat = QLineEdit()
        self.jpeg_gps_lon = QLineEdit()
        
        for widget in [self.jpeg_image_id, self.jpeg_dimensions, self.jpeg_width, 
                      self.jpeg_height, self.jpeg_h_resolution, self.jpeg_v_resolution,
                      self.jpeg_bit_depth, self.jpeg_camera_model, self.jpeg_camera_maker,
                      self.jpeg_iso, self.jpeg_shutter, self.jpeg_fnumber, self.jpeg_focal,
                      self.jpeg_gps_lat, self.jpeg_gps_lon]:
            widget.setStyleSheet("background-color: #252525; color: white; padding: 5px; border: 1px solid #555;")
        
        image_layout.addRow("Image ID:", self.jpeg_image_id)
        image_layout.addRow("Dimensions:", self.jpeg_dimensions)
        image_layout.addRow("Width:", self.jpeg_width)
        image_layout.addRow("Height:", self.jpeg_height)
        image_layout.addRow("Horizontal resolution:", self.jpeg_h_resolution)
        image_layout.addRow("Vertical resolution:", self.jpeg_v_resolution)
        image_layout.addRow("Bit depth:", self.jpeg_bit_depth)
        image_layout.addRow("Camera Model:", self.jpeg_camera_model)
        image_layout.addRow("Camera Maker:", self.jpeg_camera_maker)
        image_layout.addRow("ISO Speed:", self.jpeg_iso)
        image_layout.addRow("Shutter Speed:", self.jpeg_shutter)
        image_layout.addRow("F-Number:", self.jpeg_fnumber)
        image_layout.addRow("Focal Length:", self.jpeg_focal)
        image_layout.addRow("GPS Latitude:", self.jpeg_gps_lat)
        image_layout.addRow("GPS Longitude:", self.jpeg_gps_lon)
        image_group.setLayout(image_layout)
        layout.addWidget(image_group)
        
        layout.addStretch()
        content.setLayout(layout)
        scroll.setWidget(content)
        
        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        w.setLayout(main_layout)
        return w

    def create_png_widget(self):
        """PNG metadata widget"""
        w = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        content = QWidget()
        layout = QVBoxLayout()
        
        # Description group
        desc_group = QGroupBox("Description")
        desc_group.setStyleSheet("QGroupBox { font-weight: bold; color: #4a9eff; }")
        desc_layout = QFormLayout()
        
        self.png_title = QLineEdit()
        self.png_rating = QSpinBox()
        self.png_rating.setMaximum(5)
        self.png_tags = QLineEdit()
        self.png_comments = QTextEdit()
        self.png_comments.setMaximumHeight(80)
        
        for widget in [self.png_title, self.png_tags]:
            widget.setStyleSheet("background-color: #252525; color: white; padding: 5px; border: 1px solid #555;")
        self.png_comments.setStyleSheet("background-color: #252525; color: white; border: 1px solid #555;")
        
        desc_layout.addRow("Title:", self.png_title)
        desc_layout.addRow("Rating:", self.png_rating)
        desc_layout.addRow("Tags:", self.png_tags)
        desc_layout.addRow("Comments:", self.png_comments)
        desc_group.setLayout(desc_layout)
        layout.addWidget(desc_group)
        
        # Origin group
        origin_group = QGroupBox("Origin")
        origin_group.setStyleSheet("QGroupBox { font-weight: bold; color: #4a9eff; }")
        origin_layout = QFormLayout()
        
        self.png_authors = QLineEdit()
        self.png_date_taken = QLineEdit()
        self.png_program = QLineEdit()
        self.png_date_acquired = QLineEdit()
        self.png_copyright = QLineEdit()
        
        for widget in [self.png_authors, self.png_date_taken, self.png_program,
                      self.png_date_acquired, self.png_copyright]:
            widget.setStyleSheet("background-color: #252525; color: white; padding: 5px; border: 1px solid #555;")
        
        origin_layout.addRow("Authors:", self.png_authors)
        origin_layout.addRow("Date taken:", self.png_date_taken)
        origin_layout.addRow("Program name:", self.png_program)
        origin_layout.addRow("Date acquired:", self.png_date_acquired)
        origin_layout.addRow("Copyright:", self.png_copyright)
        origin_group.setLayout(origin_layout)
        layout.addWidget(origin_group)
        
        # Image group
        image_group = QGroupBox("Image")
        image_group.setStyleSheet("QGroupBox { font-weight: bold; color: #4a9eff; }")
        image_layout = QFormLayout()
        
        self.png_image_id = QLineEdit()
        self.png_dimensions = QLineEdit()
        self.png_dimensions.setReadOnly(True)
        self.png_width = QLineEdit()
        self.png_width.setReadOnly(True)
        self.png_height = QLineEdit()
        self.png_height.setReadOnly(True)
        self.png_h_resolution = QLineEdit()
        self.png_h_resolution.setReadOnly(True)
        self.png_v_resolution = QLineEdit()
        self.png_v_resolution.setReadOnly(True)
        self.png_bit_depth = QLineEdit()
        self.png_bit_depth.setReadOnly(True)
        self.png_gamma = QLineEdit()
        
        for widget in [self.png_image_id, self.png_dimensions, self.png_width,
                      self.png_height, self.png_h_resolution, self.png_v_resolution,
                      self.png_bit_depth, self.png_gamma]:
            widget.setStyleSheet("background-color: #252525; color: white; padding: 5px; border: 1px solid #555;")
        
        image_layout.addRow("Image ID:", self.png_image_id)
        image_layout.addRow("Dimensions:", self.png_dimensions)
        image_layout.addRow("Width:", self.png_width)
        image_layout.addRow("Height:", self.png_height)
        image_layout.addRow("Horizontal resolution:", self.png_h_resolution)
        image_layout.addRow("Vertical resolution:", self.png_v_resolution)
        image_layout.addRow("Bit depth:", self.png_bit_depth)
        image_layout.addRow("Gamma:", self.png_gamma)
        image_group.setLayout(image_layout)
        layout.addWidget(image_group)
        
        layout.addStretch()
        content.setLayout(layout)
        scroll.setWidget(content)
        
        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        w.setLayout(main_layout)
        return w

    def create_mp3_widget(self):
        """MP3 metadata widget"""
        w = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        content = QWidget()
        layout = QVBoxLayout()
        
        # Cover Art section
        art_group = QGroupBox("Cover Art")
        art_group.setStyleSheet("QGroupBox { font-weight: bold; color: #4a9eff; }")
        art_layout = QHBoxLayout()
        
        self.lbl_art = QLabel("No Cover Art")
        self.lbl_art.setFixedSize(150, 150)
        self.lbl_art.setStyleSheet("border: 2px dashed #555; background-color: #1e1e1e; color: #888;")
        self.lbl_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        btn_art = QPushButton("Change Cover")
        btn_art.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: white;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #555;
            }
        """)
        btn_art.clicked.connect(self.change_art)
        
        art_layout.addStretch()
        art_layout.addWidget(self.lbl_art)
        art_layout.addWidget(btn_art)
        art_layout.addStretch()
        art_group.setLayout(art_layout)
        layout.addWidget(art_group)
        
        # Description group
        desc_group = QGroupBox("Description")
        desc_group.setStyleSheet("QGroupBox { font-weight: bold; color: #4a9eff; }")
        desc_layout = QFormLayout()
        
        self.mp3_title = QLineEdit()
        self.mp3_subtitle = QLineEdit()
        self.mp3_rating = QSpinBox()
        self.mp3_rating.setMaximum(5)
        self.mp3_comments = QTextEdit()
        self.mp3_comments.setMaximumHeight(80)
        
        for widget in [self.mp3_title, self.mp3_subtitle]:
            widget.setStyleSheet("background-color: #252525; color: white; padding: 5px; border: 1px solid #555;")
        self.mp3_comments.setStyleSheet("background-color: #252525; color: white; border: 1px solid #555;")
        
        desc_layout.addRow("Title:", self.mp3_title)
        desc_layout.addRow("Subtitle:", self.mp3_subtitle)
        desc_layout.addRow("Rating:", self.mp3_rating)
        desc_layout.addRow("Comments:", self.mp3_comments)
        desc_group.setLayout(desc_layout)
        layout.addWidget(desc_group)
        
        # Media group
        media_group = QGroupBox("Media")
        media_group.setStyleSheet("QGroupBox { font-weight: bold; color: #4a9eff; }")
        media_layout = QFormLayout()
        
        self.mp3_artist = QLineEdit()
        self.mp3_album_artist = QLineEdit()
        self.mp3_album = QLineEdit()
        self.mp3_year = QLineEdit()
        self.mp3_track = QLineEdit()
        self.mp3_genre = QLineEdit()
        self.mp3_length = QLineEdit()
        self.mp3_length.setReadOnly(True)
        self.mp3_composer = QLineEdit()
        self.mp3_disc = QLineEdit()
        
        for widget in [self.mp3_artist, self.mp3_album_artist, self.mp3_album,
                      self.mp3_year, self.mp3_track, self.mp3_genre, self.mp3_length,
                      self.mp3_composer, self.mp3_disc]:
            widget.setStyleSheet("background-color: #252525; color: white; padding: 5px; border: 1px solid #555;")
        
        media_layout.addRow("Contributing artists:", self.mp3_artist)
        media_layout.addRow("Album artist:", self.mp3_album_artist)
        media_layout.addRow("Album:", self.mp3_album)
        media_layout.addRow("Year:", self.mp3_year)
        media_layout.addRow("#:", self.mp3_track)
        media_layout.addRow("Genre:", self.mp3_genre)
        media_layout.addRow("Length:", self.mp3_length)
        media_layout.addRow("Composer:", self.mp3_composer)
        media_layout.addRow("Disc Number:", self.mp3_disc)
        media_group.setLayout(media_layout)
        layout.addWidget(media_group)
        
        # Audio group
        audio_group = QGroupBox("Audio")
        audio_group.setStyleSheet("QGroupBox { font-weight: bold; color: #4a9eff; }")
        audio_layout = QFormLayout()
        
        self.mp3_bitrate = QLineEdit()
        self.mp3_bitrate.setReadOnly(True)
        self.mp3_channels = QLineEdit()
        self.mp3_channels.setReadOnly(True)
        self.mp3_sample_rate = QLineEdit()
        self.mp3_sample_rate.setReadOnly(True)
        
        for widget in [self.mp3_bitrate, self.mp3_channels, self.mp3_sample_rate]:
            widget.setStyleSheet("background-color: #252525; color: white; padding: 5px; border: 1px solid #555;")
        
        audio_layout.addRow("Bitrate:", self.mp3_bitrate)
        audio_layout.addRow("Channels:", self.mp3_channels)
        audio_layout.addRow("Audio sample rate:", self.mp3_sample_rate)
        audio_group.setLayout(audio_layout)
        layout.addWidget(audio_group)
        
        # Origin group
        origin_group = QGroupBox("Origin")
        origin_group.setStyleSheet("QGroupBox { font-weight: bold; color: #4a9eff; }")
        origin_layout = QFormLayout()
        
        self.mp3_software = QLineEdit()
        self.mp3_copyright = QLineEdit()
        
        for widget in [self.mp3_software, self.mp3_copyright]:
            widget.setStyleSheet("background-color: #252525; color: white; padding: 5px; border: 1px solid #555;")
        
        origin_layout.addRow("Software:", self.mp3_software)
        origin_layout.addRow("Copyright:", self.mp3_copyright)
        origin_group.setLayout(origin_layout)
        layout.addWidget(origin_group)
        
        layout.addStretch()
        content.setLayout(layout)
        scroll.setWidget(content)
        
        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        w.setLayout(main_layout)
        return w

    def setup_custom_tab(self):
        """Custom tags tab for all file types"""
        w = QWidget()
        layout = QVBoxLayout()
        
        info_label = QLabel("💡 Add custom metadata tags (TXXX for MP3, iTXt for PNG, UserComment for JPEG)")
        info_label.setStyleSheet("padding: 10px; background-color: #2a2a2a; color: #aaa; border-radius: 4px;")
        layout.addWidget(info_label)
        
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Tag name", "text"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #252525;
                color: white;
                gridline-color: #444;
                border: 1px solid #555;
            }
            QTableWidget::item:selected {
                background-color: #0d7377;
            }
            QHeaderView::section {
                background-color: #1e1e1e;
                color: white;
                padding: 5px;
                border: 1px solid #444;
            }
        """)
        layout.addWidget(self.table)
        
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("(+) Add Tag")
        btn_remove = QPushButton("(-) Add Tag")
        
        btn_add.clicked.connect(lambda: self.table.insertRow(self.table.rowCount()))
        btn_remove.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()) if self.table.currentRow() >= 0 else None)
        
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_remove)
        layout.addLayout(btn_layout)
        
        w.setLayout(layout)
        return w

    # ==========================================
    # PUBLIC API METHODS
    # ==========================================
    
    def load_file(self, filepath):
        """Load file metadata into the editor"""
        if not os.path.exists(filepath):
            QMessageBox.warning(self, "Error", f"File not found: {filepath}")
            return
        
        self.current_file = filepath
        self.pending_cover_art = None
        self.btn_save.setEnabled(True)
        
        # Update file label
        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath) / 1024  # KB
        
        # Read metadata
        data = MetadataHandler.read_metadata(filepath)
        ftype = data["type"]
        
        # Switch to appropriate widget
        if ftype == 'JPEG':
            self.stack.setCurrentIndex(1)
            self.load_jpeg_data(data)
        elif ftype == 'PNG':
            self.stack.setCurrentIndex(2)
            self.load_png_data(data)
        elif ftype == 'MP3':
            self.stack.setCurrentIndex(3)
            self.load_mp3_data(data)
        else:
            self.stack.setCurrentIndex(0)
        
        # Load custom tags
        self.table.setRowCount(0)
        for k, v in data["custom"]:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(k))
            self.table.setItem(r, 1, QTableWidgetItem(v))

    def load_jpeg_data(self, data):
        """Load JPEG metadata"""
        desc = data["description"]
        self.jpeg_title.setText(desc.get("Title", ""))
        self.jpeg_subject.setText(desc.get("Subject", ""))
        self.jpeg_tags.setText(desc.get("Tags", ""))
        self.jpeg_comments.setText(desc.get("Comments", ""))
        
        origin = data["origin"]
        self.jpeg_authors.setText(origin.get("Authors", ""))
        self.jpeg_date_taken.setText(origin.get("Date taken", ""))
        self.jpeg_program.setText(origin.get("Program name", ""))
        self.jpeg_date_acquired.setText(origin.get("Date acquired", ""))
        self.jpeg_copyright.setText(origin.get("Copyright", ""))
        
        image = data["image"]
        self.jpeg_image_id.setText(image.get("Image ID", ""))
        self.jpeg_dimensions.setText(image.get("Dimensions", ""))
        self.jpeg_width.setText(image.get("Width", ""))
        self.jpeg_height.setText(image.get("Height", ""))
        self.jpeg_h_resolution.setText(image.get("Horizontal resolution", ""))
        self.jpeg_v_resolution.setText(image.get("Vertical resolution", ""))
        self.jpeg_bit_depth.setText(image.get("Bit depth", ""))
        self.jpeg_camera_model.setText(image.get("Camera Model", ""))
        self.jpeg_camera_maker.setText(image.get("Camera Maker", ""))
        self.jpeg_iso.setText(image.get("ISO Speed", ""))
        self.jpeg_shutter.setText(image.get("Shutter Speed", ""))
        self.jpeg_fnumber.setText(image.get("F-Number", ""))
        self.jpeg_focal.setText(image.get("Focal Length", ""))
        self.jpeg_gps_lat.setText(image.get("GPS Latitude", ""))
        self.jpeg_gps_lon.setText(image.get("GPS Longitude", ""))

    def load_png_data(self, data):
        """Load PNG metadata"""
        desc = data["description"]
        self.png_title.setText(desc.get("Title", ""))
        self.png_tags.setText(desc.get("Tags", ""))
        self.png_comments.setText(desc.get("Comments", ""))
        
        origin = data["origin"]
        self.png_authors.setText(origin.get("Authors", ""))
        self.png_date_taken.setText(origin.get("Date taken", ""))
        self.png_program.setText(origin.get("Program name", ""))
        self.png_date_acquired.setText(origin.get("Date acquired", ""))
        self.png_copyright.setText(origin.get("Copyright", ""))
        
        image = data["image"]
        self.png_image_id.setText(image.get("Image ID", ""))
        self.png_dimensions.setText(image.get("Dimensions", ""))
        self.png_width.setText(image.get("Width", ""))
        self.png_height.setText(image.get("Height", ""))
        self.png_h_resolution.setText(image.get("Horizontal resolution", ""))
        self.png_v_resolution.setText(image.get("Vertical resolution", ""))
        self.png_bit_depth.setText(image.get("Bit depth", ""))
        self.png_gamma.setText(image.get("Gamma", ""))

    def load_mp3_data(self, data):
        """Load MP3 metadata"""
        desc = data["description"]
        self.mp3_title.setText(desc.get("Title", ""))
        self.mp3_subtitle.setText(desc.get("Subtitle", ""))
        self.mp3_comments.setText(desc.get("Comments", ""))
        
        media = data["media"]
        self.mp3_artist.setText(media.get("Contributing artists", ""))
        self.mp3_album_artist.setText(media.get("Album artist", ""))
        self.mp3_album.setText(media.get("Album", ""))
        self.mp3_year.setText(media.get("Year", ""))
        self.mp3_track.setText(media.get("#", ""))
        self.mp3_genre.setText(media.get("Genre", ""))
        self.mp3_length.setText(media.get("Length", ""))
        self.mp3_composer.setText(media.get("Composer", ""))
        self.mp3_disc.setText(media.get("Disc Number", ""))
        
        audio = data["audio"]
        self.mp3_bitrate.setText(audio.get("Bitrate", ""))
        self.mp3_channels.setText(audio.get("Channels", ""))
        self.mp3_sample_rate.setText(audio.get("Audio sample rate", ""))
        
        origin = data["origin"]
        self.mp3_software.setText(origin.get("Software", ""))
        self.mp3_copyright.setText(origin.get("Copyright", ""))
        
        # Cover art
        if data.get("cover_art"):
            pix = QPixmap()
            pix.loadFromData(data["cover_art"])
            self.lbl_art.setPixmap(pix.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio, 
                                             Qt.TransformationMode.SmoothTransformation))
        else:
            self.lbl_art.setText("No Cover Art")

    def change_art(self):
        """Change cover art for MP3"""
        f, _ = QFileDialog.getOpenFileName(self, "Select Cover Image", "", "Images (*.jpg *.jpeg *.png)")
        if f:
            with open(f, 'rb') as rb:
                self.pending_cover_art = rb.read()
            pix = QPixmap(f)
            self.lbl_art.setPixmap(pix.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))

    def save_file(self):
        """Save metadata to file with Dialog (Save As)"""
        if not self.current_file:
            return
        
        # 1. เตรียม Filter ให้ตรงกับไฟล์ปัจจุบัน (เช่นถ้าเปิด jpg ก็ควรให้ save เป็น jpg)
        current_ext = os.path.splitext(self.current_file)[1].lower()
        file_filter = f"Current Type (*{current_ext});;All Files (*.*)"
        
        # 2. เปิด Dialog เลือกที่ Save
        target_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Save As...", 
            self.current_file, # ใส่ path เดิมเป็น default
            file_filter
        )

        # 3. ถ้ากดยกเลิก (target_path เป็นค่าว่าง) ให้จบการทำงาน
        if not target_path:
            return

        # 4. (สำคัญ) ถ้า Save เป็นไฟล์ใหม่ ต้อง Copy ไฟล์ต้นฉบับไปที่ใหม่ก่อน
        # เพราะ MetadataHandler ของคุณทำงานแบบแก้ไขไฟล์ที่มีอยู่แล้ว
        if target_path != self.current_file:
            try:
                shutil.copy2(self.current_file, target_path)
            except Exception as e:
                QMessageBox.critical(self, "Copy Error", f"Could not create new file:\n{e}")
                return

        # --- รวบรวมข้อมูล (ส่วนนี้เหมือนเดิม) ---
        idx = self.stack.currentIndex()
        data = {"description": {}, "origin": {}, "image": {}, "media": {}, "audio": {}, "custom": []}
        
        if idx == 1:  # JPEG
            data["description"] = {
                "Title": self.jpeg_title.text(),
                "Subject": self.jpeg_subject.text(),
                "Rating": str(self.jpeg_rating.value()),
                "Tags": self.jpeg_tags.text(),
                "Comments": self.jpeg_comments.toPlainText()
            }
            data["origin"] = {
                "Authors": self.jpeg_authors.text(),
                "Date taken": self.jpeg_date_taken.text(),
                "Program name": self.jpeg_program.text(),
                "Date acquired": self.jpeg_date_acquired.text(),
                "Copyright": self.jpeg_copyright.text()
            }
            data["image"] = {
                "Image ID": self.jpeg_image_id.text(),
                "Camera Model": self.jpeg_camera_model.text(),
                "Camera Maker": self.jpeg_camera_maker.text(),
                "ISO Speed": self.jpeg_iso.text(),
                "Shutter Speed": self.jpeg_shutter.text(),
                "F-Number": self.jpeg_fnumber.text(),
                "Focal Length": self.jpeg_focal.text()
            }
            
        elif idx == 2:  # PNG
            data["description"] = {
                "Title": self.png_title.text(),
                "Rating": str(self.png_rating.value()),
                "Tags": self.png_tags.text(),
                "Comments": self.png_comments.toPlainText()
            }
            data["origin"] = {
                "Authors": self.png_authors.text(),
                "Date taken": self.png_date_taken.text(),
                "Program name": self.png_program.text(),
                "Date acquired": self.png_date_acquired.text(),
                "Copyright": self.png_copyright.text()
            }
            
        elif idx == 3:  # MP3
            data["description"] = {
                "Title": self.mp3_title.text(),
                "Subtitle": self.mp3_subtitle.text(),
                "Rating": str(self.mp3_rating.value()),
                "Comments": self.mp3_comments.toPlainText()
            }
            data["media"] = {
                "Contributing artists": self.mp3_artist.text(),
                "Album artist": self.mp3_album_artist.text(),
                "Album": self.mp3_album.text(),
                "Year": self.mp3_year.text(),
                "#": self.mp3_track.text(),
                "Genre": self.mp3_genre.text(),
                "Composer": self.mp3_composer.text(),
                "Disc Number": self.mp3_disc.text()
            }
            data["origin"] = {
                "Software": self.mp3_software.text(),
                "Copyright": self.mp3_copyright.text()
            }
            if self.pending_cover_art:
                data["cover_art_data"] = self.pending_cover_art
        
        # Custom tags
        for r in range(self.table.rowCount()):
            k_item = self.table.item(r, 0)
            v_item = self.table.item(r, 1)
            if k_item and v_item and k_item.text():
                data["custom"].append((k_item.text(), v_item.text()))
        
        # --- ส่ง target_path ไปบันทึก (แทน self.current_file) ---
        ok, msg = MetadataHandler.save_metadata(target_path, data)
        
        if ok:
            QMessageBox.information(self, "✅ Success", 
                                  f"Metadata saved successfully!\n\nSaved to: {os.path.basename(target_path)}")
            
            # อัปเดตให้โปรแกรมย้ายไปทำงานกับไฟล์ใหม่ที่เพิ่งเซฟ
            self.current_file = target_path
            self.load_file(self.current_file)  # Refresh UI
        else:
            QMessageBox.critical(self, "❌ Error", f"Failed to save metadata:\n\n{msg}")


# ==========================================
# 3. STANDALONE APPLICATION (FOR TESTING)
# ==========================================
if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication, QMainWindow, QFileDialog, QMenuBar, QMenu
    from PyQt6.QtGui import QAction
    import sys
    
    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Advanced Metadata Editor")
            self.setGeometry(100, 100, 900, 700)
            
            # Create metadata widget
            self.editor = MetadataEditorWidget()
            self.setCentralWidget(self.editor)
            
            # Create menu
            menubar = self.menuBar()
            file_menu = menubar.addMenu("File")
            
            open_action = QAction("Open File...", self)
            open_action.setShortcut("Ctrl+O")
            open_action.triggered.connect(self.open_file)
            file_menu.addAction(open_action)
            
            file_menu.addSeparator()
            
            exit_action = QAction("Exit", self)
            exit_action.setShortcut("Ctrl+Q")
            exit_action.triggered.connect(self.close)
            file_menu.addAction(exit_action)
            
            # Apply dark theme
            self.setStyleSheet(DARK_STYLE)
        
        def open_file(self):
            filepath, _ = QFileDialog.getOpenFileName(
                self,
                "Select Media File",
                "",
                "Media Files (*.jpg *.jpeg *.png *.mp3);;All Files (*.*)"
            )
            if filepath:
                self.editor.load_file(filepath)
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
