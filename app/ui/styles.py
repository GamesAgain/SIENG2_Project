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