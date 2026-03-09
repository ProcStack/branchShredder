from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QComboBox, QTextEdit, 
                             QPushButton, QListWidget, QFileDialog, QColorDialog,
                             QDoubleSpinBox)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor
from models import EventType

class SettingsSidebar(QWidget):
    settingsChanged = pyqtSignal()
    
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.layout = QVBoxLayout(self)
        
        self.layout.addWidget(QLabel("PROJECT SETTINGS"))
        
        # Color pickers for each node type
        for event_type_val in EventType.list():
            row = QHBoxLayout()
            label = QLabel(f"{event_type_val}:")
            btn = QPushButton()
            btn.setFixedWidth(50)
            btn.setStyleSheet(f"background-color: {self.settings.node_colors[event_type_val]}")
            def make_color_picker(val, b):
                def pick():
                    color = QColorDialog.getColor(QColor(self.settings.node_colors[val]))
                    if color.isValid():
                        hex_color = color.name()
                        self.settings.node_colors[val] = hex_color
                        b.setStyleSheet(f"background-color: {hex_color}")
                        self.settingsChanged.emit()
                return pick
            btn.clicked.connect(make_color_picker(event_type_val, btn))
            row.addWidget(label)
            row.addWidget(btn)
            self.layout.addLayout(row)

        # Scale SpinBox
        self.layout.addWidget(QLabel("BG Image Max Scale:"))
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(1.0, 10.0)
        self.scale_spin.setSingleStep(0.5)
        self.scale_spin.setValue(self.settings.bg_image_scale)
        self.scale_spin.valueChanged.connect(self.update_scale)
        self.layout.addWidget(self.scale_spin)
        
        self.layout.addStretch()

    def update_scale(self, val):
        self.settings.bg_image_scale = val
        self.settingsChanged.emit()

class StoryWritingBar(QWidget):
    contentChanged = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.node = None
        self.layout = QHBoxLayout(self)
        
        # Left side: Editor
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        
        # Markdown toolbar
        toolbar_layout = QHBoxLayout()
        self.btn_bold = QPushButton("B")
        self.btn_bold.setFixedWidth(30)
        self.btn_bold.clicked.connect(lambda: self.insert_markdown("**", "**"))
        
        self.btn_italic = QPushButton("I")
        self.btn_italic.setFixedWidth(30)
        self.btn_italic.clicked.connect(lambda: self.insert_markdown("*", "*"))

        self.btn_underline = QPushButton("U")
        self.btn_underline.setFixedWidth(30)
        self.btn_underline.clicked.connect(lambda: self.insert_markdown("__", "__"))

        spacerA = QWidget()
        spacerA.setFixedWidth(20)

        self.btn_h1 = QPushButton("H1")
        self.btn_h1.setFixedWidth(30)
        self.btn_h1.clicked.connect(lambda: self.insert_markdown("# ", ""))

        self.btn_h2 = QPushButton("H2")
        self.btn_h2.setFixedWidth(30)
        self.btn_h2.clicked.connect(lambda: self.insert_markdown("## ", ""))

        self.btn_h3 = QPushButton("H3")
        self.btn_h3.setFixedWidth(30)
        self.btn_h3.clicked.connect(lambda: self.insert_markdown("### ", ""))

        self.btn_h4 = QPushButton("H4")
        self.btn_h4.setFixedWidth(30)
        self.btn_h4.clicked.connect(lambda: self.insert_markdown("#### ", ""))

        spacerB = QWidget()
        spacerB.setFixedWidth(20)
        
        self.btn_link = QPushButton("URL")
        self.btn_link.setFixedWidth(50)
        self.btn_link.clicked.connect(lambda: self.insert_markdown("[Name](", ")"))

        self.btn_media = QPushButton("Media")
        self.btn_media.setFixedWidth(50)
        self.btn_media.clicked.connect(lambda: self.insert_markdown("![Alt](", ")"))
        
        toolbar_layout.addWidget(self.btn_bold)
        toolbar_layout.addWidget(self.btn_italic)
        toolbar_layout.addWidget(self.btn_underline)
        toolbar_layout.addWidget(spacerA)
        toolbar_layout.addWidget(self.btn_h1)
        toolbar_layout.addWidget(self.btn_h2)
        toolbar_layout.addWidget(self.btn_h3)
        toolbar_layout.addWidget(self.btn_h4)
        toolbar_layout.addWidget(spacerB)
        toolbar_layout.addWidget(self.btn_link)
        toolbar_layout.addWidget(self.btn_media)
        toolbar_layout.addStretch()
        
        self.text_editor = QTextEdit()
        self.text_editor.textChanged.connect(self.update_node_content)
        
        editor_layout.addLayout(toolbar_layout)
        editor_layout.addWidget(self.text_editor)
        
        # Right side: Characters and Stage Notes
        right_sidebar = QWidget()
        right_sidebar.setFixedWidth(200)
        right_layout = QVBoxLayout(right_sidebar)
        
        right_layout.addWidget(QLabel("CHARACTERS"))
        self.char_list = QListWidget()
        right_layout.addWidget(self.char_list)
        
        right_layout.addWidget(QLabel("STAGE NOTES"))
        self.stage_notes = QTextEdit()
        self.stage_notes.textChanged.connect(self.update_node_stage_notes)
        right_layout.addWidget(self.stage_notes)
        
        self.layout.addWidget(editor_widget, 4)
        self.layout.addWidget(right_sidebar, 1)

    def set_node(self, node_data, all_character_names):
        self.node = node_data
        if not node_data:
            self.setEnabled(False)
            self.text_editor.clear()
            self.stage_notes.clear()
            self.char_list.clear()
            return

        self.setEnabled(True)
        self.text_editor.blockSignals(True)
        self.stage_notes.blockSignals(True)
        self.text_editor.setPlainText(node_data.markdown_content)
        self.stage_notes.setPlainText(node_data.stage_notes)
        self.text_editor.blockSignals(False)
        self.stage_notes.blockSignals(False)
        
        self.char_list.clear()
        self.char_list.addItems(sorted(list(set(all_character_names))))

    def insert_markdown(self, prefix, suffix):
        cursor = self.text_editor.textCursor()
        text = cursor.selectedText()
        cursor.insertText(f"{prefix}{text}{suffix}")

    def update_node_content(self):
        if self.node:
            self.node.markdown_content = self.text_editor.toPlainText()

    def update_node_stage_notes(self):
        if self.node:
            self.node.stage_notes = self.stage_notes.toPlainText()

class NodeInspector(QWidget):
    nodeChanged = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.node = None
        
        self.layout = QVBoxLayout(self)
        
        self.name_label = QLabel("Node Name:")
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self.update_node_name)
        self.layout.addWidget(self.name_label)
        self.layout.addWidget(self.name_edit)

        # Character Names (for Input Nodes)
        self.char_input_label = QLabel("Character Names (comma separated):")
        self.char_input_edit = QTextEdit()
        self.char_input_edit.setFixedHeight(60)
        self.char_input_edit.textChanged.connect(self.update_node_characters)
        self.layout.addWidget(self.char_input_label)
        self.layout.addWidget(self.char_input_edit)
        
        self.type_label = QLabel("Event Type:")
        self.type_combo = QComboBox()
        self.type_combo.addItems(EventType.list())
        self.type_combo.currentTextChanged.connect(self.update_node_type)
        self.layout.addWidget(self.type_label)
        self.layout.addWidget(self.type_combo)
        
        self.zone_label = QLabel("Location Zone:")
        self.zone_edit = QLineEdit()
        self.zone_edit.textChanged.connect(self.update_node_zone)
        self.layout.addWidget(self.zone_label)
        self.layout.addWidget(self.zone_edit)
        
        self.actions_label = QLabel("Game Scene Actions:")
        self.actions_edit = QTextEdit()
        self.actions_edit.textChanged.connect(self.update_node_actions)
        self.layout.addWidget(self.actions_label)
        self.layout.addWidget(self.actions_edit)
        
        self.media_label = QLabel("Media Assets:")
        self.media_list = QListWidget()
        self.layout.addWidget(self.media_label)
        self.layout.addWidget(self.media_list)
        
        media_btns = QHBoxLayout()
        self.add_media_btn = QPushButton("Add Media")
        self.add_media_btn.clicked.connect(self.add_media)
        self.remove_media_btn = QPushButton("Remove Selected")
        self.remove_media_btn.clicked.connect(self.remove_media)
        media_btns.addWidget(self.add_media_btn)
        media_btns.addWidget(self.remove_media_btn)
        self.layout.addLayout(media_btns)
        
        self.set_bg_btn = QPushButton("Set Background Image")
        self.set_bg_btn.clicked.connect(self.set_background_image)
        self.layout.addWidget(self.set_bg_btn)
        
        self.layout.addStretch()

    def set_node(self, node_data):
        self.node = node_data
        if not node_data:
            self.setEnabled(False)
            return
        
        self.setEnabled(True)
        # Block signals to avoid recursive updates while setting initial values
        self.name_edit.blockSignals(True)
        self.type_combo.blockSignals(True)
        self.char_input_edit.blockSignals(True)
        
        self.name_edit.setText(node_data.name)
        
        # Hide/Show Character input
        is_start = node_data.event_type == EventType.START
        self.char_input_label.setVisible(is_start)
        self.char_input_edit.setVisible(is_start)
        self.char_input_edit.setPlainText(", ".join(node_data.character_names))

        self.type_combo.setCurrentText(node_data.event_type.value)
        self.zone_edit.setText(node_data.location_zone)
        self.actions_edit.setPlainText(node_data.scene_actions)
        self.media_list.clear()
        self.media_list.addItems(node_data.media_paths)

        self.name_edit.blockSignals(False)
        self.type_combo.blockSignals(False)
        self.char_input_edit.blockSignals(False)

    def update_node_characters(self):
        if self.node:
            content = self.char_input_edit.toPlainText()
            self.node.character_names = [c.strip() for c in content.split(",") if c.strip()]
            self.nodeChanged.emit()

    def update_node_name(self, text):
        if self.node:
            self.node.name = text
            self.nodeChanged.emit()

    def update_node_type(self, text):
        if self.node:
            self.node.event_type = EventType(text)
            is_start = self.node.event_type == EventType.START
            self.char_input_label.setVisible(is_start)
            self.char_input_edit.setVisible(is_start)
            self.nodeChanged.emit()

    def update_node_zone(self, text):
        if self.node:
            self.node.location_zone = text

    def update_node_actions(self):
        if self.node:
            self.node.scene_actions = self.actions_edit.toPlainText()

    def add_media(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Open Media Assets")
        if files:
            self.node.media_paths.extend(files)
            self.media_list.addItems(files)

    def remove_media(self):
        current_row = self.media_list.currentRow()
        if current_row >= 0:
            item = self.media_list.takeItem(current_row)
            self.node.media_paths.remove(item.text())

    def set_background_image(self):
        if self.media_list.currentItem():
            path = self.media_list.currentItem().text()
            self.node.image_path = path
            self.node.show_bg_image = not self.node.show_bg_image
            self.nodeChanged.emit()


class ConnectionInspector(QWidget):
    connectionChanged = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.conn_item = None
        
        self.layout = QVBoxLayout(self)
        self.layout.addWidget(QLabel("CONNECTION PROPERTIES"))
        
        # Line style dropdown
        self.style_label = QLabel("Line Style:")
        self.style_combo = QComboBox()
        self._pen_styles = {
            "No Pen": Qt.PenStyle.NoPen,
            "Solid": Qt.PenStyle.SolidLine,
            "Dash": Qt.PenStyle.DashLine,
            "Dot": Qt.PenStyle.DotLine,
            "Dash-Dot": Qt.PenStyle.DashDotLine,
            "Dash-Dot-Dot": Qt.PenStyle.DashDotDotLine,
        }
        self.style_combo.addItems(self._pen_styles.keys())
        self.style_combo.setCurrentText("Solid")
        self.style_combo.currentTextChanged.connect(self.update_line_style)
        self.layout.addWidget(self.style_label)
        self.layout.addWidget(self.style_combo)
        
        # Color picker
        self.color_label = QLabel("Line Color:")
        self.color_btn = QPushButton()
        self.color_btn.setFixedWidth(50)
        self.color_btn.clicked.connect(self.pick_color)
        self.layout.addWidget(self.color_label)
        self.layout.addWidget(self.color_btn)
        
        self.layout.addStretch()

    def set_connection(self, conn_item):
        self.conn_item = conn_item
        if not conn_item:
            self.setEnabled(False)
            return
        
        self.setEnabled(True)
        self.style_combo.blockSignals(True)
        for name, style in self._pen_styles.items():
            if style == conn_item.line_style:
                self.style_combo.setCurrentText(name)
                break
        self.color_btn.setStyleSheet(f"background-color: {conn_item.line_color}")
        self.style_combo.blockSignals(False)

    def update_line_style(self, text):
        if self.conn_item and text in self._pen_styles:
            self.conn_item.line_style = self._pen_styles[text]
            self.conn_item.update()
            self.connectionChanged.emit()

    def pick_color(self):
        if self.conn_item:
            color = QColorDialog.getColor(QColor(self.conn_item.line_color))
            if color.isValid():
                self.conn_item.line_color = color.name()
                self.color_btn.setStyleSheet(f"background-color: {color.name()}")
                self.conn_item.update()
                self.connectionChanged.emit()
