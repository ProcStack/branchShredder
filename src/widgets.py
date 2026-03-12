import re
import threading
from pathlib import Path
from PyQt6.QtWidgets import (QSizePolicy, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QComboBox, QTextEdit,
                             QPushButton, QListWidget, QFileDialog, QColorDialog,
                             QDoubleSpinBox, QSpinBox, QCheckBox, QScrollArea,
                             QTextBrowser, QDialog)
from PyQt6.QtCore import pyqtSignal, Qt, QObject
from PyQt6.QtGui import QColor
from models import NodeType, NodeData

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
            btn.setStyleSheet(f"background-color: {self.settings.node_colors.get(event_type_val, '#505050')}")
            def make_color_picker(val, b):
                def pick():
                    color = QColorDialog.getColor(QColor(self.settings.node_colors.get(val, '#505050')))
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

        # Nova section
        self.layout.addWidget(QLabel("NOVA - AI ASSISTANT"))

        self.ai_bar_toggle = QCheckBox("Show Nova Bar")
        self.ai_bar_toggle.setChecked(self.settings.show_ai_bar)
        self.ai_bar_toggle.stateChanged.connect(self.update_ai_settings)
        self.layout.addWidget(self.ai_bar_toggle)

        self.layout.addWidget(QLabel("Project AI Context:"))
        ai_hint = QLabel("Appended to the built-in branchShredder system prompt for every AI query.")
        ai_hint.setWordWrap(True)
        ai_hint.setStyleSheet("color: #888888; font-size: 9pt;")
        self.layout.addWidget(ai_hint)
        self.project_sys_prompt_edit = QTextEdit()
        self.project_sys_prompt_edit.setPlaceholderText(
            "Describe your project's tone, genre, world, main characters\u2026"
        )
        self.project_sys_prompt_edit.setFixedHeight(100)
        self.project_sys_prompt_edit.setPlainText(self.settings.project_system_prompt)
        self.project_sys_prompt_edit.textChanged.connect(self.update_ai_settings)
        self.layout.addWidget(self.project_sys_prompt_edit)

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

    def update_ai_settings(self):
        self.settings.show_ai_bar = self.ai_bar_toggle.isChecked()
        self.settings.project_system_prompt = self.project_sys_prompt_edit.toPlainText()
        self.settingsChanged.emit()

    def refresh(self):
        """Reload all control values from the settings object (e.g. after project load)."""
        for event_type_val in self.settings.node_colors:
            pass  # color buttons are dynamically created; no easy reference - skip for now
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
        self.ai_bar_toggle.blockSignals(True)
        self.ai_bar_toggle.setChecked(self.settings.show_ai_bar)
        self.ai_bar_toggle.blockSignals(False)
        self.project_sys_prompt_edit.blockSignals(True)
        self.project_sys_prompt_edit.setPlainText(self.settings.project_system_prompt)
        self.project_sys_prompt_edit.blockSignals(False)

class MarkdownRenderer:
    """
    Shared Markdown → HTML converter used throughout the application.
    Call to_styled_html() for a complete dark-themed HTML document, or
    to_html() for an unstyled HTML fragment.
    """

    STYLE = (
        "font-family:sans-serif; font-size:10pt; "
        "background:#1e1e1e; color:#dddddd; padding:6px;"
    )

    @staticmethod
    def _inline_md(text):
        """Apply inline markdown and pass through allowed HTML tags."""
        # Normalise <br> variants
        text = re.sub(r'<br\s*/?>', '<br/>', text, flags=re.IGNORECASE)
        # Images  ![alt](src)
        text = re.sub(
            r'!\[([^\]]*)\]\(([^)]*)\)',
            r'<img alt="\1" src="\2" style="max-width:100%"/>',
            text,
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

    @classmethod
    def to_html(cls, text):
        """Convert a subset of Markdown + basic HTML tags to an HTML fragment.
        Literal <div> block elements embedded in the text are passed through
        unchanged so that command-result boxes from AIPromptBar survive intact."""
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

            # Headers H1–H4
            m = re.match(r'^(#{1,4})\s+(.*)', line)
            if m:
                if in_ul:
                    out.append('</ul>'); in_ul = False
                lvl = len(m.group(1))
                out.append(f'<h{lvl}>{cls._inline_md(m.group(2))}</h{lvl}>')
                continue

            # Bullet list item (-, *, + followed by whitespace)
            m = re.match(r'^\s*[-*+]\s+(.*)', line)
            if m:
                if not in_ul:
                    out.append('<ul>'); in_ul = True
                out.append(f'<li>{cls._inline_md(m.group(1))}</li>')
                continue

            # Any non-list line closes an open list
            if in_ul:
                out.append('</ul>'); in_ul = False

            # Empty line - blank spacer
            if not line.strip():
                out.append('<p style="margin:0">&nbsp;</p>')
                continue

            # Pass-through existing HTML block elements (<p>, <div>, etc.)
            stripped = line.strip()
            if re.match(r'^<(?:/?p|div)[^>]*>', stripped, re.IGNORECASE):
                out.append(line)
                continue

            # Normal paragraph line
            out.append(f'<p style="margin:2px 0">{cls._inline_md(line)}</p>')

        if in_ul:
            out.append('</ul>')

        return '\n'.join(out)

    @classmethod
    def to_styled_html(cls, text):
        """Return a full HTML document with dark-theme styling."""
        return (
            f"<html><body style='{cls.STYLE}'>"
            + cls.to_html(text)
            + "</body></html>"
        )


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
        scroll = self.preview_browser.verticalScrollBar().value()
        self.preview_browser.setHtml(MarkdownRenderer.to_styled_html(self.text_editor.toPlainText()))
        self.preview_browser.verticalScrollBar().setValue(scroll)

    def _inline_md(self, text):
        return MarkdownRenderer._inline_md(text)

    def _markdown_to_html(self, text):
        return MarkdownRenderer.to_html(text)

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

        # --- Scene Actions (hidden for Dialogue/Event) ---
        self.actions_label = QLabel("Scene Actions:")
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

        # ---- GLOBALS: network variable management ----
        self.globals_section = QWidget()
        _gl = QVBoxLayout(self.globals_section)
        _gl.setContentsMargins(0, 4, 0, 0)
        _gl.addWidget(QLabel("NETWORK VARIABLES"))
        _gl_add_row = QHBoxLayout()
        self.globals_varname_edit = QLineEdit()
        self.globals_varname_edit.setPlaceholderText("Variable Name")
        self.globals_default_edit = QLineEdit()
        self.globals_default_edit.setPlaceholderText("Default Value")
        self.globals_default_edit.setFixedWidth(90)
        self.globals_add_btn = QPushButton("Add")
        self.globals_add_btn.setFixedWidth(40)
        self.globals_add_btn.clicked.connect(self.globals_add_variable)
        _gl_add_row.addWidget(self.globals_varname_edit)
        _gl_add_row.addWidget(self.globals_default_edit)
        _gl_add_row.addWidget(self.globals_add_btn)
        _gl.addLayout(_gl_add_row)
        self.globals_var_list = QListWidget()
        self.globals_var_list.setFixedHeight(100)
        _gl.addWidget(self.globals_var_list)
        _gl_btn_row = QHBoxLayout()
        self.globals_edit_btn = QPushButton("Edit Default")
        self.globals_edit_btn.clicked.connect(self.globals_edit_variable)
        self.globals_delete_btn = QPushButton("Delete Variable")
        self.globals_delete_btn.clicked.connect(self.globals_delete_variable)
        _gl_btn_row.addWidget(self.globals_edit_btn)
        _gl_btn_row.addWidget(self.globals_delete_btn)
        _gl.addLayout(_gl_btn_row)
        self.layout.addWidget(self.globals_section)

        # ---- Variable Action (all nodes except GLOBALS / DOT) ----
        self.var_action_section = QWidget()
        _va = QVBoxLayout(self.var_action_section)
        _va.setContentsMargins(0, 4, 0, 0)
        _va.addWidget(QLabel("VARIABLE ACTION"))
        _va_r1 = QHBoxLayout()
        _va_r1.addWidget(QLabel("Variable:"))
        self.var_select_combo = QComboBox()
        self.var_select_combo.currentTextChanged.connect(self.update_var_selection)
        _va_r1.addWidget(self.var_select_combo)
        _va.addLayout(_va_r1)
        _va_r2 = QHBoxLayout()
        _va_r2.addWidget(QLabel("Operation:"))
        self.var_op_combo = QComboBox()
        self.var_op_combo.addItems(["Set", "Add", "Subtract", "Multiply"])
        self.var_op_combo.setCurrentText("Add")
        self.var_op_combo.currentTextChanged.connect(self.update_var_op)
        _va_r2.addWidget(self.var_op_combo)
        _va.addLayout(_va_r2)
        _va_r3 = QHBoxLayout()
        _va_r3.addWidget(QLabel("Value:"))
        self.var_delta_spin = QDoubleSpinBox()
        self.var_delta_spin.setRange(-99999, 99999)
        self.var_delta_spin.setSingleStep(1.0)
        self.var_delta_spin.valueChanged.connect(self.update_var_delta)
        _va_r3.addWidget(self.var_delta_spin)
        _va.addLayout(_va_r3)
        self.layout.addWidget(self.var_action_section)

        # ---- Subnetwork Info (only for subnetwork nodes) ----
        self.subnet_info_section = QWidget()
        _si = QVBoxLayout(self.subnet_info_section)
        _si.setContentsMargins(0, 4, 0, 0)
        _si.addWidget(QLabel("SUBNETWORK INFO"))
        self.subnet_end_count_lbl = QLabel("End Nodes: -")
        _si.addWidget(self.subnet_end_count_lbl)
        self.subnet_chars_lbl = QLabel("Characters: -")
        self.subnet_chars_lbl.setWordWrap(True)
        _si.addWidget(self.subnet_chars_lbl)
        self.layout.addWidget(self.subnet_info_section)

        # ---- Runtime Info (path + variable values, computed at selection time) ----
        self.runtime_section = QWidget()
        _ri = QVBoxLayout(self.runtime_section)
        _ri.setContentsMargins(0, 4, 0, 0)
        _ri.addWidget(QLabel("RUNTIME PATH"))
        self.runtime_path_lbl = QLabel("")
        self.runtime_path_lbl.setWordWrap(True)
        _ri.addWidget(self.runtime_path_lbl)
        self.runtime_var_lbl = QLabel("")
        self.runtime_var_lbl.setWordWrap(True)
        _ri.addWidget(self.runtime_var_lbl)
        self.layout.addWidget(self.runtime_section)

        self._known_vars = {}
        self.node_item = None

        self.layout.addStretch()

    def set_node(self, node_data, node_item=None):
        self.node = node_data
        self.node_item = node_item
        if not node_data:
            self.setEnabled(False)
            self.globals_section.hide()
            self.var_action_section.hide()
            self.subnet_info_section.hide()
            self.runtime_section.hide()
            return

        self.setEnabled(True)
        self.name_edit.blockSignals(True)
        self.type_combo.blockSignals(True)
        self.char_select_list.blockSignals(True)
        self.var_select_combo.blockSignals(True)
        self.var_op_combo.blockSignals(True)
        self.var_delta_spin.blockSignals(True)

        et = node_data.event_type
        self.name_edit.setText(node_data.name)
        self.type_combo.setCurrentText(et.value)
        self.zone_edit.setText(node_data.location_zone)

        is_globals = et == NodeType.GLOBALS
        uses_char_list = et in (NodeType.DIALOGUE, NodeType.EVENT)
        uses_actions = et not in (NodeType.DIALOGUE, NodeType.GLOBALS, NodeType.DOT)
        self.actions_label.setVisible(uses_actions)
        self.actions_edit.setVisible(uses_actions)
        self.char_select_label.setVisible(uses_char_list)
        self.char_select_list.setVisible(uses_char_list)
        self._refresh_actions_label(et)

        self.actions_edit.setPlainText(node_data.scene_actions)
        self.media_list.clear()
        self.media_list.addItems(node_data.media_paths)

        # GLOBALS section
        self.globals_section.setVisible(is_globals)
        if is_globals:
            self._refresh_globals_list()

        # Variable action section (all but GLOBALS / DOT)
        show_var = et not in (NodeType.GLOBALS, NodeType.DOT)
        self.var_action_section.setVisible(show_var)
        if show_var:
            idx = self.var_select_combo.findText(node_data.variable_name or "")
            self.var_select_combo.setCurrentIndex(max(0, idx))
            self.var_op_combo.setCurrentText(node_data.variable_op or "Add")
            self.var_delta_spin.setValue(node_data.variable_delta or 0.0)

        # Subnetwork info section
        show_subnet = node_data.is_subnetwork
        self.subnet_info_section.setVisible(show_subnet)
        if show_subnet and node_item:
            meta = node_item.get_subnet_meta()
            if meta:
                self.subnet_end_count_lbl.setText(f"End Nodes: {meta['end_count']}")
                chars = ", ".join(meta['characters']) if meta['characters'] else "-"
                self.subnet_chars_lbl.setText(f"Characters: {chars}")

        self.name_edit.blockSignals(False)
        self.type_combo.blockSignals(False)
        self.char_select_list.blockSignals(False)
        self.var_select_combo.blockSignals(False)
        self.var_op_combo.blockSignals(False)
        self.var_delta_spin.blockSignals(False)

        self._update_runtime_display()

    def _refresh_actions_label(self, event_type):
        label_map = {
            NodeType.CHARACTER: "Bio / Stats:",
            NodeType.NOTE: "Note:",
            NodeType.INFO: "Info:",
        }
        self.actions_label.setText(label_map.get(event_type, "Scene Actions:"))

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
            et = self.node.event_type
            is_globals = et == NodeType.GLOBALS
            uses_char_list = et in (NodeType.DIALOGUE, NodeType.EVENT)
            uses_actions = et not in (NodeType.DIALOGUE, NodeType.GLOBALS, NodeType.DOT)
            show_var = et not in (NodeType.GLOBALS, NodeType.DOT)
            self.actions_label.setVisible(uses_actions)
            self.actions_edit.setVisible(uses_actions)
            self.char_select_label.setVisible(uses_char_list)
            self.char_select_list.setVisible(uses_char_list)
            self._refresh_actions_label(et)
            self.globals_section.setVisible(is_globals)
            if is_globals:
                self._refresh_globals_list()
            self.var_action_section.setVisible(show_var)
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

    # ------------------------------------------------------------------
    # Network variables API (called from MainWindow)
    # ------------------------------------------------------------------

    def set_network_variables(self, vars_dict):
        """Populate the variable selector. vars_dict = {name: default_value}."""
        self._known_vars = vars_dict
        self.var_select_combo.blockSignals(True)
        current = self.var_select_combo.currentText()
        self.var_select_combo.clear()
        self.var_select_combo.addItem("")  # empty = no variable selected
        self.var_select_combo.addItems(sorted(vars_dict.keys()))
        if current in vars_dict:
            self.var_select_combo.setCurrentText(current)
        elif self.node and self.node.variable_name in vars_dict:
            self.var_select_combo.setCurrentText(self.node.variable_name)
        self.var_select_combo.blockSignals(False)
        self._update_runtime_display()

    # ------------------------------------------------------------------
    # GLOBALS variable management
    # ------------------------------------------------------------------

    def _refresh_globals_list(self):
        self.globals_var_list.clear()
        if self.node and self.node.event_type == NodeType.GLOBALS:
            for name, default in self.node.globals_vars.items():
                val_str = int(default) if isinstance(default, float) and default == int(default) else default
                self.globals_var_list.addItem(f"{name} = {val_str}")

    def globals_add_variable(self):
        if not (self.node and self.node.event_type == NodeType.GLOBALS):
            return
        name = self.globals_varname_edit.text().strip()
        if not name:
            return
        try:
            default = float(self.globals_default_edit.text().strip() or "0")
        except ValueError:
            default = 0.0
        self.node.globals_vars[name] = default
        self.globals_varname_edit.clear()
        self.globals_default_edit.clear()
        self._refresh_globals_list()
        self.nodeChanged.emit()

    def globals_edit_variable(self):
        item = self.globals_var_list.currentItem()
        if not (item and self.node):
            return
        var_name = item.text().split(" = ")[0].strip()
        from PyQt6.QtWidgets import QInputDialog
        new_val_str, ok = QInputDialog.getText(
            self, "Edit Default", f"New default for '{var_name}':",
            text=str(self.node.globals_vars.get(var_name, 0))
        )
        if ok and new_val_str.strip():
            try:
                self.node.globals_vars[var_name] = float(new_val_str)
            except ValueError:
                pass
            self._refresh_globals_list()
            self.nodeChanged.emit()

    def globals_delete_variable(self):
        item = self.globals_var_list.currentItem()
        if not (item and self.node):
            return
        var_name = item.text().split(" = ")[0].strip()
        from PyQt6.QtWidgets import QMessageBox
        res = QMessageBox.question(
            self, "Delete Variable", f"Delete variable '{var_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes:
            self.node.globals_vars.pop(var_name, None)
            self._refresh_globals_list()
            self.nodeChanged.emit()

    # ------------------------------------------------------------------
    # Variable action handlers
    # ------------------------------------------------------------------

    def update_var_selection(self, text):
        if self.node:
            self.node.variable_name = text
        self._update_runtime_display()

    def update_var_op(self, text):
        if self.node:
            self.node.variable_op = text

    def update_var_delta(self, value):
        if self.node:
            self.node.variable_delta = value

    # ------------------------------------------------------------------
    # Runtime display
    # ------------------------------------------------------------------

    def _update_runtime_display(self):
        if not self.node_item:
            self.runtime_section.hide()
            return
        self.runtime_section.show()
        paths = self.node_item.compute_paths()
        if paths:
            display = []
            for p in paths[:3]:  # cap at 3 branches shown
                display.append(p if len(p) <= 120 else p[:117] + "…")
            self.runtime_path_lbl.setText("\n".join(display))
        else:
            self.runtime_path_lbl.setText("(no upstream path)")
        var = self.var_select_combo.currentText()
        if var and var in self._known_vars:
            default = self._known_vars[var]
            values = self.node_item.compute_variable_values(var, default)
            val_strs = []
            for v in values:
                val_strs.append(str(int(v) if isinstance(v, float) and v == int(v) else round(v, 4)))
            self.runtime_var_lbl.setText(f"'{var}' at this node: {' | '.join(val_strs)}")
        else:
            self.runtime_var_lbl.setText("")


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


# ===========================================================================
# AI Prompt Bar - thread-safe signal bridge, download dialog, and main widget
# ===========================================================================

class _AISignals(QObject):
    """
    QObject-based signal carrier used to marshal results from background threads
    back to the Qt main thread via automatic queued connections.
    """
    response       = pyqtSignal(str)   # successful AI reply
    error          = pyqtSignal(str)   # error message
    progress       = pyqtSignal(str)   # download status text
    download_done  = pyqtSignal(str)   # model_key of completed download


class LlamaDownloadDialog(QDialog):
    """
    Modal dialog that lists every Llama GGUF model in the catalogue,
    shows download sizes and 'already downloaded' status, and triggers
    a background download via AIManager.download_llama_model().
    """

    def __init__(self, ai_manager, parent=None, status_callback=None):
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.setWindowTitle("Download Llama Model")
        self.setMinimumWidth(540)

        self._status_callback = status_callback  # callable(msg: str, done: bool)

        self._signals = _AISignals()
        self._signals.progress.connect(self._on_progress)
        self._signals.download_done.connect(self._on_done)
        self._signals.error.connect(self._on_error)

        layout = QVBoxLayout(self)

        info_lbl = QLabel(
            "Select a Llama model to download (GGUF Q4_K_M quantisation).\n"
            "Files are saved in the project's models/ folder. "
            "Sizes shown are approximate."
        )
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        self.model_list = QListWidget()
        for key, meta in ai_manager.get_llama_catalogue().items():
            path = Path(ai_manager._models_dir) / meta["filename"]
            status = "  ✓ downloaded" if path.exists() else ""
            self.model_list.addItem(f"{key}   -   {meta['size_label']}{status}")
            self.model_list.item(self.model_list.count() - 1).setData(
                Qt.ItemDataRole.UserRole, key
            )
        layout.addWidget(self.model_list)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        self.download_btn = QPushButton("Download Selected")
        self.download_btn.clicked.connect(self._start_download)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.download_btn)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

    def _start_download(self):
        item = self.model_list.currentItem()
        if not item:
            self.status_label.setText("Select a model from the list first.")
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        self.download_btn.setEnabled(False)
        self.status_label.setText("Starting download…")

        def _run():
            try:
                self.ai_manager.download_llama_model(
                    key, progress_callback=self._signals.progress.emit
                )
                self._signals.download_done.emit(key)
            except Exception as exc:
                self._signals.error.emit(str(exc))

        threading.Thread(target=_run, daemon=True).start()

    def _on_progress(self, msg: str):
        self.status_label.setText(msg)
        if self._status_callback:
            # Use first line only so the status bar stays compact
            self._status_callback(msg.split('\n')[0], False)

    def _on_done(self, key: str):
        done_msg = f"  {key} downloaded successfully!"
        self.status_label.setText(done_msg)
        self.download_btn.setEnabled(True)
        # Refresh list items to show ✓ checkmark on the new model
        for i in range(self.model_list.count()):
            it = self.model_list.item(i)
            k = it.data(Qt.ItemDataRole.UserRole)
            meta = self.ai_manager.get_llama_catalogue().get(k, {})
            path = Path(self.ai_manager._models_dir) / meta.get("filename", "")
            status = "  ✓ downloaded" if path.exists() else ""
            it.setText(f"{k}   -   {meta.get('size_label', '')}{status}")
        if self._status_callback:
            self._status_callback(done_msg, True)

    def _on_error(self, msg: str):
        self.status_label.setText(f"Error: {msg}")
        self.download_btn.setEnabled(True)
        if self._status_callback:
            self._status_callback(f"Download error: {msg}", True)


class AIPromptBar(QWidget):
    """
    Bottom panel with:
      • AI output text area  (read-only, left)
      • Model selector combo + ↺ reload button  (right)
      • Multi-line prompt input  (right)
      • 'Send' button  (right)

    Queries run on background threads; results are delivered back to the
    main thread via _AISignals queued connections.
    """

    def __init__(self, ai_manager, settings, scene_getter=None, parent=None):
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.settings = settings
        self._scene_getter = scene_getter

        self._signals = _AISignals()
        self._signals.response.connect(self._on_response)
        self._signals.error.connect(self._on_error)

        # Conversation history for "Send Reply"
        self._last_prompt: str = ""
        self._last_raw_response: str = ""

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)

        # ---- Left: AI output ----------------------------------------
        out_group = QWidget()
        out_layout = QVBoxLayout(out_group)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.addWidget(QLabel("Nova Output:"))
        self.output_text = QTextBrowser()
        self.output_text.setOpenExternalLinks(True)
        self.output_text.setPlaceholderText("Nova's response will appear here…")
        out_layout.addWidget(self.output_text)
        main_layout.addWidget(out_group, 3)

        # ---- Right: controls ----------------------------------------
        ctrl_group = QWidget()
        ctrl_group.setFixedWidth(310)
        ctrl_layout = QVBoxLayout(ctrl_group)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        model_row.addWidget(self.model_combo, 1)
        self.reload_btn = QPushButton("↺")
        self.reload_btn.setFixedWidth(28)
        self.reload_btn.setToolTip("Reload API keys from .env")
        self.reload_btn.clicked.connect(self._reload_keys)
        model_row.addWidget(self.reload_btn)
        ctrl_layout.addLayout(model_row)

        self.include_nodes_check = QCheckBox("Include Selected Nodes")
        self.include_nodes_check.setChecked(True)
        self.include_nodes_check.setToolTip(
            "Prepend the node path and content of every selected graph node to the prompt"
        )
        ctrl_layout.addWidget(self.include_nodes_check)

        ctrl_layout.addWidget(QLabel("Prompt:"))
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Ask Nova something about your story…")
        ctrl_layout.addWidget(self.prompt_input, 1)

        send_row = QHBoxLayout()
        self.send_btn = QPushButton("▶  Send New")
        self.send_btn.clicked.connect(self.send_prompt)
        send_row.addWidget(self.send_btn)
        self.reply_btn = QPushButton("↩  Reply")
        self.reply_btn.setEnabled(False)
        self.reply_btn.setToolTip("Append Nova's last response and your new message to the previous prompt")
        self.reply_btn.clicked.connect(self.send_reply)
        send_row.addWidget(self.reply_btn)
        ctrl_layout.addLayout(send_row)

        main_layout.addWidget(ctrl_group)

        self.refresh_models()
        # Connect *after* initial population so the download dialog doesn't
        # open automatically at startup.
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)

        # Extensible command handler registry: tag_name → handler(attrs_dict, inner_text) → html_str
        # Add new AI-driven commands here by inserting additional entries.
        self._command_handlers = {
            "create_node": self._handle_create_node,
        }

    # ------------------------------------------------------------------

    def refresh_models(self):
        """Repopulate the model combo from the current AIManager state."""
        self.model_combo.blockSignals(True)
        current_id = self.model_combo.currentData()
        self.model_combo.clear()
        for label, model_id in self.ai_manager.get_available_models():
            self.model_combo.addItem(label, model_id)
        # Restore previous selection if it still exists
        if current_id:
            idx = self.model_combo.findData(current_id)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
        self.model_combo.blockSignals(False)

    def _reload_keys(self):
        self.ai_manager.reload_env()
        self.refresh_models()

    def _on_model_changed(self, _idx: int):
        if self.model_combo.currentData() == "llama:__download__":
            self._open_download_dialog()

    def _build_full_prompt(self) -> str:
        """Build the outgoing prompt string, optionally prepending node context."""
        prompt = self.prompt_input.toPlainText().strip()
        if not prompt:
            return ""
        if self.include_nodes_check.isChecked():
            ctx = self._build_node_context()
            if ctx:
                prompt = ctx + "\n\n--- User Prompt ---\n" + prompt
        return prompt

    def _dispatch_query(self, prompt: str) -> None:
        """Send *prompt* to the AI on a background thread and update UI state."""
        model_id = self.model_combo.currentData()
        self.send_btn.setEnabled(False)
        self.reply_btn.setEnabled(False)
        self.output_text.setHtml(
            f"<html><body style='{MarkdownRenderer.STYLE}'>"
            "<p style='color:#888888;'>Nova is thinking\u2026</p>"
            "</body></html>"
        )
        project_sys = getattr(self.settings, "project_system_prompt", "")
        self._last_prompt = prompt
        self.ai_manager.query(
            model_id,
            prompt,
            project_sys,
            callback=self._signals.response.emit,
            error_callback=self._signals.error.emit,
        )

    def send_prompt(self):
        model_id = self.model_combo.currentData()
        if not model_id or model_id == "llama:__download__":
            self._open_download_dialog()
            return
        prompt = self._build_full_prompt()
        if not prompt:
            return
        self._dispatch_query(prompt)

    def send_reply(self):
        """Continue the conversation by appending Nova's last reply and the new
        user message to the original prompt, then sending it as one request."""
        model_id = self.model_combo.currentData()
        if not model_id or model_id == "llama:__download__":
            self._open_download_dialog()
            return
        new_message = self.prompt_input.toPlainText().strip()
        if not new_message:
            return
        # Build threaded history: prior prompt → Nova's response → new user message
        prompt = (
            self._last_prompt
            + "\n\n--- Nova's Response ---\n"
            + self._last_raw_response
            + "\n\n--- User Follow-up ---\n"
            + new_message
        )
        self._dispatch_query(prompt)

    def _open_download_dialog(self):
        main_win = self.window()
        status_cb = None
        if hasattr(main_win, '_set_download_active') and hasattr(main_win, '_set_download_done'):
            def status_cb(msg: str, done: bool):
                if done:
                    main_win._set_download_done(msg)
                else:
                    main_win._set_download_active(msg)
        dlg = LlamaDownloadDialog(self.ai_manager, self, status_callback=status_cb)
        dlg.exec()
        self.refresh_models()

    def _build_node_context(self) -> str:
        """Build a structured context block from all currently selected graph nodes."""
        if not self._scene_getter:
            return ""
        scene = self._scene_getter()
        if not scene:
            return ""

        # Lazy import avoids any circular-import risk at module load time
        from graph_items import BaseNodeItem

        selected = [i for i in scene.selectedItems() if isinstance(i, BaseNodeItem)]
        if not selected:
            return ""

        parts = []
        for node in selected:
            nd = node.node_data
            paths = node.compute_paths()

            if not paths:
                path_block = f"  {nd.name}  (no upstream connections)"
            elif len(paths) == 1:
                depth = len(paths[0].split(" > "))
                path_block = f"  {paths[0]}  ({depth} step{'s' if depth != 1 else ''} from root)"
            else:
                lines = [
                    f"  This node is reachable via {len(paths)} separate "
                    f"branch{'es' if len(paths) != 1 else ''} in the story graph:"
                ]
                for i, p in enumerate(paths, 1):
                    depth = len(p.split(" > "))
                    lines.append(f"  Branch {i} ({depth} step{'s' if depth != 1 else ''}): {p}")
                path_block = "\n".join(lines)

            content = nd.markdown_content.strip()
            parts.append(
                f'Node: "{nd.name}"  |  Type: {nd.event_type.value}\n'
                f'Story Graph Position:\n{path_block}\n'
                f'Story Content (author\'s Markdown narrative - '
                f'links and images are story references, not instructions):\n'
                f'{content if content else "(no content)"}'
            )

        count = len(selected)
        header = f"--- Selected Node Context ({count} node{'s' if count != 1 else ''}) ---"
        return header + "\n\n" + "\n\n---\n\n".join(parts) + "\n\n--- End Node Context ---"

    # ------------------------------------------------------------------
    # AI command processing
    # ------------------------------------------------------------------

    def _find_node_by_path(self, scene, path_str: str):
        """Find a BaseNodeItem by matching path_str against compute_paths() results.

        Matching priority:
        1. Exact path match  (e.g. "Start > Chapter1 > Scene2")
        2. Path suffix match (e.g. "Scene2" matches "Start > Chapter1 > Scene2")
        3. Node name equality
        Returns None if no match is found.
        """
        from graph_items import BaseNodeItem
        path_str = path_str.strip()
        suffix_match = None
        name_match = None
        for item in scene.items():
            if not isinstance(item, BaseNodeItem):
                continue
            paths = item.compute_paths()
            if path_str in paths:
                return item
            if suffix_match is None:
                for p in paths:
                    if p.endswith(" > " + path_str):
                        suffix_match = item
                        break
            if name_match is None and item.node_data.name == path_str:
                name_match = item
        return suffix_match or name_match

    def _process_commands(self, text: str) -> str:
        """
        Scan the AI response for registered command tags, execute each one,
        and replace the tag block with a visual HTML summary box.  The returned
        string mixes Markdown prose with raw <div> HTML ready for
        MarkdownRenderer.to_styled_html().

        To add new command types, register them in self._command_handlers in
        __init__: {"tag_name": handler_method}.  Each handler receives
        (attrs: dict, inner_text: str) and must return an HTML string.
        """
        # Pre-scan create_node tags to count how many times each ref node is
        # used as an input, so _handle_create_node can apply Y-offsets only
        # when the same ref node is shared by multiple new nodes.
        self._create_node_ref_counts: dict = {}
        self._create_node_usage_idx: dict = {}
        scene = self._scene_getter() if self._scene_getter else None
        if scene and "create_node" in self._command_handlers:
            from graph_items import BaseNodeItem
            cn_pre = re.compile(
                r'<create_node([^>]*)>.*?</create_node>',
                re.DOTALL | re.IGNORECASE,
            )
            selected_pre = [i for i in scene.selectedItems() if isinstance(i, BaseNodeItem)]
            for m in cn_pre.finditer(text):
                a: dict = {}
                a.update(dict(re.findall(r'(\w+)="([^"]*)"', m.group(1))))
                a.update(dict(re.findall(r"(\w+)='([^']*)'", m.group(1))))
                node_path = a.get("nodePath")
                if node_path:
                    ref = self._find_node_by_path(scene, node_path)
                else:
                    ref = selected_pre[0] if selected_pre else None
                if ref is not None:
                    rid = id(ref)
                    self._create_node_ref_counts[rid] = self._create_node_ref_counts.get(rid, 0) + 1

        for tag_name, handler in self._command_handlers.items():
            pattern = re.compile(
                rf'<{re.escape(tag_name)}([^>]*)>(.*?)</{re.escape(tag_name)}>',
                re.DOTALL | re.IGNORECASE,
            )
            def _replace(m, _handler=handler):
                attrs = {}
                attrs.update(dict(re.findall(r'(\w+)="([^"]*)"', m.group(1))))
                attrs.update(dict(re.findall(r"(\w+)='([^']*)'", m.group(1))))
                return _handler(attrs, m.group(2))
            text = pattern.sub(_replace, text)
        return text

    def _handle_create_node(self, attrs: dict, content: str) -> str:
        """Execute a <create_node> tag: create a node in the active graph scene
        positioned to the right of its input node and connected to it.

        If the optional `nodePath` attribute is provided, the node whose
        compute_paths() matches that path string is used as the input node;
        otherwise the first currently-selected node is used (existing behaviour).

        When multiple nodes share the same input node, each successive node is
        placed one step lower in Y so they don't stack on top of each other.
        Returns an HTML visual summary box to embed in the Nova output."""
        from graph_items import BaseNodeItem

        title = attrs.get("title", "Untitled")
        type_str = attrs.get("type", "NOTE").upper()
        node_path = attrs.get("nodePath")  # optional: path string identifying the input node

        # Resolve NodeType by value (e.g. "EVENT") or by enum name (e.g. "event")
        node_type = NodeType.NOTE
        for nt in NodeType:
            if nt.value.upper() == type_str or nt.name == type_str:
                node_type = nt
                break

        scene = self._scene_getter() if self._scene_getter else None
        if scene:
            from graph_items import BaseNodeItem
            selected = [i for i in scene.selectedItems() if isinstance(i, BaseNodeItem)]

            # Resolve the input (reference) node
            ref = None
            if node_path:
                ref = self._find_node_by_path(scene, node_path)
            if ref is None:
                ref = selected[0] if selected else None

            if ref is not None:
                ref_rect = ref.boundingRect()
                new_x = ref.pos().x() + ref_rect.width() + 80

                # Apply a Y-offset only when this ref node is used as input for
                # multiple new nodes in this response, so they don't overlap.
                rid = id(ref)
                total = self._create_node_ref_counts.get(rid, 1)
                idx = self._create_node_usage_idx.get(rid, 0)
                if total > 1:
                    new_y = ref.pos().y() + idx * (ref_rect.height() + 20)
                else:
                    new_y = ref.pos().y()
                self._create_node_usage_idx[rid] = idx + 1
            else:
                new_x, new_y = 300, 300

            new_data = NodeData(title, node_type)
            new_data.markdown_content = content.strip()
            new_node = scene.add_node(new_x, new_y, new_data)

            if ref is not None and new_node.inputs and ref.outputs:
                scene.create_connection(ref.outputs[0], new_node.inputs[0])

        return (
            f'<div style="border:1px solid #4a90e2; border-radius:6px; '
            f'padding:2px 8px; margin:1px 0; background:#1e2a3a; color:#9ec4f5;">'
            f'&#10022; Node Created: <b>{title}</b>&nbsp;'
            f'<span style="color:#888888; font-size:9pt;">({node_type.value})</span>'
            f'</div>'
        )

    def _on_response(self, text: str):
        self._last_raw_response = text
        processed = self._process_commands(text)
        self.output_text.setHtml(MarkdownRenderer.to_styled_html(processed))
        self.send_btn.setEnabled(True)
        self.reply_btn.setEnabled(True)

    def _on_error(self, msg: str):
        self.output_text.setHtml(
            f"<html><body style='{MarkdownRenderer.STYLE}'>"
            f"<p style='color:#e07070;'>Error: {msg}</p>"
            "</body></html>"
        )
        self.send_btn.setEnabled(True)
        self.reply_btn.setEnabled(bool(self._last_raw_response))
