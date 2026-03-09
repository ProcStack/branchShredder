import re
from PyQt6.QtWidgets import (QSizePolicy, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QComboBox, QTextEdit, 
                             QPushButton, QListWidget, QFileDialog, QColorDialog,
                             QDoubleSpinBox, QSpinBox, QCheckBox, QScrollArea,
                             QTextBrowser)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor
from models import NodeType

class SettingsSidebar(QWidget):
    settingsChanged = pyqtSignal()
    
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings

        # Outer layout contains only the scroll area
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMinimumHeight(0)
        self.setMinimumHeight(0)

        content_widget = QWidget()
        content_widget.setMinimumWidth(278)  # fit cleanly inside 300px sidebar
        self.layout = QVBoxLayout(content_widget)
        scroll.setWidget(content_widget)
        outer_layout.addWidget(scroll)

        self.layout.addWidget(QLabel("PROJECT SETTINGS"))
        
        # Color pickers for each node type
        for event_type_val in NodeType.list():
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

        # BG Image Offset
        row_x = QHBoxLayout()
        row_x.addWidget(QLabel("BG Image Offset X:"))
        self.offset_x_spin = QSpinBox()
        self.offset_x_spin.setRange(-1000, 1000)
        self.offset_x_spin.setValue(int(self.settings.bg_image_offset_x))
        self.offset_x_spin.valueChanged.connect(self.update_offset)
        row_x.addWidget(self.offset_x_spin)
        self.layout.addLayout(row_x)

        row_y = QHBoxLayout()
        row_y.addWidget(QLabel("BG Image Offset Y:"))
        self.offset_y_spin = QSpinBox()
        self.offset_y_spin.setRange(-1000, 1000)
        self.offset_y_spin.setValue(int(self.settings.bg_image_offset_y))
        self.offset_y_spin.valueChanged.connect(self.update_offset)
        row_y.addWidget(self.offset_y_spin)
        self.layout.addLayout(row_y)

        # Grid settings
        self.layout.addWidget(QLabel("GRID"))

        self.grid_toggle = QCheckBox("Show Grid")
        self.grid_toggle.setChecked(self.settings.show_grid)
        self.grid_toggle.stateChanged.connect(self.update_grid)
        self.layout.addWidget(self.grid_toggle)

        row_minor = QHBoxLayout()
        row_minor.addWidget(QLabel("Grid Minor Spacing:"))
        self.grid_minor_spin = QSpinBox()
        self.grid_minor_spin.setRange(10, 500)
        self.grid_minor_spin.setValue(self.settings.grid_minor)
        self.grid_minor_spin.valueChanged.connect(self.update_grid)
        row_minor.addWidget(self.grid_minor_spin)
        self.layout.addLayout(row_minor)

        row_major = QHBoxLayout()
        row_major.addWidget(QLabel("Grid Major Spacing:"))
        self.grid_major_spin = QSpinBox()
        self.grid_major_spin.setRange(10, 2000)
        self.grid_major_spin.setValue(self.settings.grid_major)
        self.grid_major_spin.valueChanged.connect(self.update_grid)
        row_major.addWidget(self.grid_major_spin)
        self.layout.addLayout(row_major)

        # Connection drop behaviour
        self.layout.addWidget(QLabel("CONNECTIONS"))
        self.drop_toggle = QCheckBox("New Node If No Curve Destination")
        self.drop_toggle.setChecked(self.settings.create_node_on_empty_drop)
        self.drop_toggle.stateChanged.connect(self.update_drop_setting)
        self.layout.addWidget(self.drop_toggle)

        row_sock = QHBoxLayout()
        row_sock.addWidget(QLabel("Socket Size:"))
        self.socket_size_spin = QSpinBox()
        self.socket_size_spin.setRange(6, 40)
        self.socket_size_spin.setValue(self.settings.socket_size)
        self.socket_size_spin.valueChanged.connect(self.update_socket_size)
        row_sock.addWidget(self.socket_size_spin)
        self.layout.addLayout(row_sock)

        self.layout.addStretch()

    def update_scale(self, val):
        self.settings.bg_image_scale = val
        self.settingsChanged.emit()

    def update_offset(self):
        self.settings.bg_image_offset_x = self.offset_x_spin.value()
        self.settings.bg_image_offset_y = self.offset_y_spin.value()
        self.settingsChanged.emit()

    def update_grid(self):
        self.settings.show_grid = self.grid_toggle.isChecked()
        self.settings.grid_minor = self.grid_minor_spin.value()
        self.settings.grid_major = self.grid_major_spin.value()
        self.settingsChanged.emit()

    def update_drop_setting(self):
        self.settings.create_node_on_empty_drop = self.drop_toggle.isChecked()

    def update_socket_size(self, val):
        self.settings.socket_size = val
        self.settingsChanged.emit()

    def refresh(self):
        """Reload all control values from the settings object (e.g. after project load)."""
        for event_type_val in self.settings.node_colors:
            pass  # color buttons are dynamically created; no easy reference — skip for now
        self.scale_spin.blockSignals(True)
        self.scale_spin.setValue(self.settings.bg_image_scale)
        self.scale_spin.blockSignals(False)
        self.offset_x_spin.blockSignals(True)
        self.offset_x_spin.setValue(int(self.settings.bg_image_offset_x))
        self.offset_x_spin.blockSignals(False)
        self.offset_y_spin.blockSignals(True)
        self.offset_y_spin.setValue(int(self.settings.bg_image_offset_y))
        self.offset_y_spin.blockSignals(False)
        self.grid_toggle.blockSignals(True)
        self.grid_toggle.setChecked(self.settings.show_grid)
        self.grid_toggle.blockSignals(False)
        self.grid_minor_spin.blockSignals(True)
        self.grid_minor_spin.setValue(self.settings.grid_minor)
        self.grid_minor_spin.blockSignals(False)
        self.grid_major_spin.blockSignals(True)
        self.grid_major_spin.setValue(self.settings.grid_major)
        self.grid_major_spin.blockSignals(False)
        self.drop_toggle.blockSignals(True)
        self.drop_toggle.setChecked(self.settings.create_node_on_empty_drop)
        self.drop_toggle.blockSignals(False)
        self.socket_size_spin.blockSignals(True)
        self.socket_size_spin.setValue(self.settings.socket_size)
        self.socket_size_spin.blockSignals(False)

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

        # Editor title
        editorText = QLabel("Content Editor; Markdown")

        spacerHeader = QWidget()
        spacerHeader.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Quick buttons for common markdown
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
        self.btn_h1.setFixedWidth(35)
        self.btn_h1.clicked.connect(lambda: self.insert_markdown("# ", ""))

        self.btn_h2 = QPushButton("H2")
        self.btn_h2.setFixedWidth(35)
        self.btn_h2.clicked.connect(lambda: self.insert_markdown("## ", ""))

        self.btn_h3 = QPushButton("H3")
        self.btn_h3.setFixedWidth(35)
        self.btn_h3.clicked.connect(lambda: self.insert_markdown("### ", ""))

        self.btn_h4 = QPushButton("H4")
        self.btn_h4.setFixedWidth(35)
        self.btn_h4.clicked.connect(lambda: self.insert_markdown("#### ", ""))

        spacerB = QWidget()
        spacerB.setFixedWidth(20)
        
        self.btn_link = QPushButton("URL")
        self.btn_link.setFixedWidth(45)
        self.btn_link.clicked.connect(lambda: self.insert_markdown("[Name](", ")"))

        self.btn_media = QPushButton("Media")
        self.btn_media.setFixedWidth(58)
        self.btn_media.clicked.connect(lambda: self.insert_markdown("![Alt](", ")"))

        spacerC = QWidget()
        spacerC.setFixedWidth(40)

        self.btn_preview = QPushButton("Toggle Preview")
        self.btn_preview.setFixedWidth(125)
        self.btn_preview.setCheckable(True)
        self.btn_preview.clicked.connect(self._toggle_preview)
        
        toolbar_layout.addWidget(editorText)
        toolbar_layout.addWidget(spacerHeader)
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
        toolbar_layout.addWidget(spacerC)
        toolbar_layout.addWidget(self.btn_preview)
        toolbar_layout.addStretch()
        
        self.text_editor = QTextEdit()
        self.text_editor.textChanged.connect(self.update_node_content)
        self.text_editor.textChanged.connect(self._on_text_changed)
        
        editor_layout.addLayout(toolbar_layout)
        editor_layout.addWidget(self.text_editor)

        # Centre: Markdown preview (hidden by default)
        self.preview_browser = QTextBrowser()
        self.preview_browser.setOpenExternalLinks(True)
        self.preview_browser.hide()
        
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
        self.layout.addWidget(self.preview_browser, 4)
        self.layout.addWidget(right_sidebar, 1)

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    def _toggle_preview(self, checked):
        self.preview_browser.setVisible(checked)
        if checked:
            self._update_preview()

    def _on_text_changed(self):
        if self.preview_browser.isVisible():
            self._update_preview()

    def _update_preview(self):
        html = self._markdown_to_html(self.text_editor.toPlainText())
        # Wrap in basic stylesheet for readability
        styled = (
            "<html><body style='font-family:sans-serif; font-size:10pt; "
            "background:#1e1e1e; color:#dddddd; padding:6px;'>" + html + "</body></html>"
        )
        scroll = self.preview_browser.verticalScrollBar().value()
        self.preview_browser.setHtml(styled)
        self.preview_browser.verticalScrollBar().setValue(scroll)

    def _inline_md(self, text):
        """Apply inline markdown and pass through allowed HTML tags."""
        # Normalise <br> variants
        text = re.sub(r'<br\s*/?>', '<br/>', text, flags=re.IGNORECASE)
        # Images  ![alt](src)
        text = re.sub(
            r'!\[([^\]]*)\]\(([^)]*)\)',
            r'<img alt="\1" src="\2" style="max-width:100%"/>',
            text
        )
        # Links  [label](url)
        text = re.sub(r'\[([^\]]+)\]\(([^)]*)\)', r'<a href="\2">\1</a>', text)
        # Bold  **text**
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        # Underline  __text__
        text = re.sub(r'__(.+?)__', r'<u>\1</u>', text)
        # Italic  *text*  (not part of **)
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
        return text

    def _markdown_to_html(self, text):
        """Convert a subset of Markdown + basic HTML tags to HTML."""
        lines = text.split('\n')
        out = []
        in_ul = False

        for line in lines:
            # Horizontal rule: 3+ identical chars (-, *, _) optionally separated by spaces
            if re.match(r'^\s*([-*_])\s*(?:\1\s*){2,}\s*$', line):
                if in_ul:
                    out.append('</ul>'); in_ul = False
                out.append('<hr/>')
                continue

            # Headers H1–H4 (longest prefix first is handled by {1,4} greedy match)
            m = re.match(r'^(#{1,4})\s+(.*)', line)
            if m:
                if in_ul:
                    out.append('</ul>'); in_ul = False
                lvl = len(m.group(1))
                out.append(f'<h{lvl}>{self._inline_md(m.group(2))}</h{lvl}>')
                continue

            # Bullet list item (-, *, + followed by whitespace)
            m = re.match(r'^\s*[-*+]\s+(.*)', line)
            if m:
                if not in_ul:
                    out.append('<ul>'); in_ul = True
                out.append(f'<li>{self._inline_md(m.group(1))}</li>')
                continue

            # Any non-list line closes an open list
            if in_ul:
                out.append('</ul>'); in_ul = False

            # Empty line — blank spacer
            if not line.strip():
                out.append('<p style="margin:0">&nbsp;</p>')
                continue

            # Pass-through lines that are already HTML block tags
            stripped = line.strip()
            if re.match(r'^</?p[^>]*>', stripped, re.IGNORECASE):
                out.append(self._inline_md(line))
                continue

            # Normal paragraph line
            out.append(f'<p style="margin:2px 0">{self._inline_md(line)}</p>')

        if in_ul:
            out.append('</ul>')

        return '\n'.join(out)

    # ------------------------------------------------------------------

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
        if self.preview_browser.isVisible():
            self._update_preview()
        
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

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.setMinimumHeight(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMinimumHeight(0)

        content_widget = QWidget()
        self.layout = QVBoxLayout(content_widget)
        scroll.setWidget(content_widget)
        outer_layout.addWidget(scroll)

        self.name_label = QLabel("Node Name:")
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self.update_node_name)
        self.layout.addWidget(self.name_label)
        self.layout.addWidget(self.name_edit)

        self.type_label = QLabel("Node Type:")
        self.type_combo = QComboBox()
        self.type_combo.addItems(NodeType.list())
        self.type_combo.currentTextChanged.connect(self.update_node_type)
        self.layout.addWidget(self.type_label)
        self.layout.addWidget(self.type_combo)
        
        self.zone_label = QLabel("Location Zone:")
        self.zone_edit = QLineEdit()
        self.zone_edit.textChanged.connect(self.update_node_zone)
        self.layout.addWidget(self.zone_label)
        self.layout.addWidget(self.zone_edit)

        # --- Game Scene Actions (hidden for Dialogue/Event) ---
        self.actions_label = QLabel("Game Scene Actions:")
        self.actions_edit = QTextEdit()
        self.actions_edit.textChanged.connect(self.update_node_actions)
        self.layout.addWidget(self.actions_label)
        self.layout.addWidget(self.actions_edit)

        # --- Character multiselect (shown only for Dialogue/Event) ---
        self.char_select_label = QLabel("Characters in Scene:")
        self.char_select_list = QListWidget()
        self.char_select_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.char_select_list.itemSelectionChanged.connect(self.update_selected_characters)
        self.layout.addWidget(self.char_select_label)
        self.layout.addWidget(self.char_select_list)
        
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
        self.name_edit.blockSignals(True)
        self.type_combo.blockSignals(True)
        self.char_select_list.blockSignals(True)
        
        self.name_edit.setText(node_data.name)

        self.type_combo.setCurrentText(node_data.event_type.value)
        self.zone_edit.setText(node_data.location_zone)

        uses_char_list = node_data.event_type in (NodeType.DIALOGUE, NodeType.EVENT)
        uses_actions = node_data.event_type != NodeType.DIALOGUE
        self.actions_label.setVisible(uses_actions)
        self.actions_edit.setVisible(uses_actions)
        self.char_select_label.setVisible(uses_char_list)
        self.char_select_list.setVisible(uses_char_list)
        self._refresh_actions_label(node_data.event_type)

        self.actions_edit.setPlainText(node_data.scene_actions)
        self.media_list.clear()
        self.media_list.addItems(node_data.media_paths)

        self.name_edit.blockSignals(False)
        self.type_combo.blockSignals(False)
        self.char_select_list.blockSignals(False)

    def _refresh_actions_label(self, event_type):
        label_map = {
            NodeType.CHARACTER: "Bio / Stats:",
            NodeType.NOTE: "Note:",
            NodeType.INFO: "Info:",
        }
        self.actions_label.setText(label_map.get(event_type, "Game Scene Actions:"))

    def set_available_characters(self, all_names):
        """Populate the character multiselect list with all known character names."""
        self.char_select_list.blockSignals(True)
        self.char_select_list.clear()
        selected = self.node.selected_characters if self.node else []
        for name in sorted(all_names):
            item = self.char_select_list.addItem(name)
            list_item = self.char_select_list.item(self.char_select_list.count() - 1)
            if name in selected:
                list_item.setSelected(True)
        self.char_select_list.blockSignals(False)

    def update_node_name(self, text):
        if self.node:
            self.node.name = text
            self.nodeChanged.emit()

    def update_node_type(self, text):
        if self.node:
            self.node.event_type = NodeType(text)
            uses_char_list = self.node.event_type in (NodeType.DIALOGUE, NodeType.EVENT)
            uses_actions = self.node.event_type != NodeType.DIALOGUE
            self.actions_label.setVisible(uses_actions)
            self.actions_edit.setVisible(uses_actions)
            self.char_select_label.setVisible(uses_char_list)
            self.char_select_list.setVisible(uses_char_list)
            self._refresh_actions_label(self.node.event_type)
            self.nodeChanged.emit()

    def update_node_zone(self, text):
        if self.node:
            self.node.location_zone = text

    def update_node_actions(self):
        if self.node:
            self.node.scene_actions = self.actions_edit.toPlainText()

    def update_selected_characters(self):
        if self.node:
            self.node.selected_characters = [item.text() for item in self.char_select_list.selectedItems()]
            self.nodeChanged.emit()

    def add_media(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Open Media Assets")
        if files and self.node.media_paths is not None:
            self.node.media_paths.extend(files)
            self.media_list.addItems(files)

    def remove_media(self):
        current_row = self.media_list.currentRow()
        if current_row >= 0:
            item = self.media_list.takeItem(current_row)
            if self.node.media_paths is not None:
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
