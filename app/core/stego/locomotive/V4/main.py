import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QTabWidget, QLineEdit)
from PyQt6.QtCore import Qt

from locomotive import StegoLogic

class StegoApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simple Stego Append (Locomotive Edition)")
        self.setGeometry(200, 200, 500, 350)
        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        title = QLabel("PNG File Appender")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)

        tabs = QTabWidget()
        self.tab_hide = QWidget()
        self.tab_extract = QWidget()
        tabs.addTab(self.tab_hide, "Hide (ซ่อน)")
        tabs.addTab(self.tab_extract, "Extract (ถอด)")
        layout.addWidget(tabs)

        self.setup_hide_tab()
        self.setup_extract_tab()

    def setup_hide_tab(self):
        layout = QVBoxLayout()
        
        # สร้าง Widget (ต้องเป็น self. เพื่อให้ locomotive เรียกใช้ได้)
        self.txt_hide_img = QLineEdit(); self.txt_hide_img.setPlaceholderText("เลือกรูป PNG ต้นฉบับ")
        btn_img = QPushButton("เลือกรูปภาพ")
        # ส่ง self ไปให้ locomotive
        btn_img.clicked.connect(lambda: StegoLogic.select_file(self, self.txt_hide_img, "Image"))
        
        self.txt_hide_secret = QLineEdit(); self.txt_hide_secret.setPlaceholderText("เลือกไฟล์ที่จะซ่อน")
        btn_secret = QPushButton("เลือกไฟล์ลับ")
        # ส่ง self ไปให้ locomotive
        btn_secret.clicked.connect(lambda: StegoLogic.select_file(self, self.txt_hide_secret, "File"))
        
        btn_start = QPushButton("เริ่มซ่อนไฟล์")
        btn_start.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        # ส่ง self ไปให้ locomotive
        btn_start.clicked.connect(lambda: StegoLogic.embed(self))

        layout.addWidget(QLabel("1. รูปภาพหลัก (PNG):"))
        layout.addLayout(self.row(self.txt_hide_img, btn_img))
        layout.addWidget(QLabel("2. ไฟล์ความลับ:"))
        layout.addLayout(self.row(self.txt_hide_secret, btn_secret))
        layout.addStretch()
        layout.addWidget(btn_start)
        self.tab_hide.setLayout(layout)

    def setup_extract_tab(self):
        layout = QVBoxLayout()
        
        self.txt_ext_img = QLineEdit(); self.txt_ext_img.setPlaceholderText("เลือกรูปที่มีไฟล์ซ่อนอยู่")
        btn_img = QPushButton("เลือกรูปภาพ")
        # ส่ง self ไปให้ locomotive
        btn_img.clicked.connect(lambda: StegoLogic.select_file(self, self.txt_ext_img, "Image"))
        
        btn_extract = QPushButton("ถอดไฟล์ออกมา")
        btn_extract.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 10px;")
        # ส่ง self ไปให้ locomotive
        btn_extract.clicked.connect(lambda: StegoLogic.run_extract(self))

        layout.addWidget(QLabel("เลือกรูปภาพเพื่อถอดข้อมูล:"))
        layout.addLayout(self.row(self.txt_ext_img, btn_img))
        layout.addStretch()
        layout.addWidget(btn_extract)
        self.tab_extract.setLayout(layout)

    def row(self, widget1, widget2):
        h = QHBoxLayout()
        h.addWidget(widget1)
        h.addWidget(widget2)
        return h

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StegoApp()
    window.show()
    sys.exit(app.exec())