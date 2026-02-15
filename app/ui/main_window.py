import sys
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QTabWidget
)


# from extract_tab import ExtractTab
# from key_tab import KeyTab
from app.ui.styles import DARK_STYLE
from app.ui.tabs.embed_tab import EmbedTab
from app.ui.tabs.embed_tab_mock import EmbedTabMockUp
from app.ui.tabs.extract_tab import ExtractTab

# ============================================================================
# MAIN APPLICATION
# ============================================================================

class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SIENG2 - Secure Incognito ENcryption Guard")
        self.resize(1000, 700)
        self.setStyleSheet(DARK_STYLE)
        
        tabs = QTabWidget()
        tabs.addTab(EmbedTab(), "Embed")
        tabs.addTab(ExtractTab(), "Extract")
        tabs.addTab(EmbedTabMockUp(), "Embed Mockup")
        
        self.setCentralWidget(tabs)


# ============================================================================
# APPLICATION ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())