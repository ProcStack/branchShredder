from PyQt6.QtWidgets import (QGraphicsItem, QGraphicsRectItem, QGraphicsLineItem,
                             QGraphicsPixmapItem, QGraphicsTextItem)
from PyQt6.QtCore import Qt, QLineF, QRectF
from PyQt6.QtGui import QPen, QBrush, QColor, QPixmap, QPainterPath, QPainterPathStroker

NODE_BAR_H = 20  # Title bar height for the SUBNETWORK mini-window shape

# Font size (pt) for the port name labels drawn inside the node body.
# Change this value manually to adjust how large the port names appear.
PORT_LABEL_FONT_SIZE = 7

# Fraction of the 0–3 RGB magnitude above which node text flips to black.
# 0.66 → flip when R/255 + G/255 + B/255 ≥ 1.98  (i.e.  ~66 % brightness).
_TEXT_CONTRAST_THRESHOLD = 0.63


def _text_color_for_bg(color_str: str) -> QColor:
    """Return white or black text color based on the background hex color.

    Magnitude = R_norm + G_norm + B_norm  (range 0–3, where each channel is /255).
    If magnitude >= _TEXT_CONTRAST_THRESHOLD * 3 the background is bright enough
    to warrant black text; otherwise white text is used.
    """
    c = QColor(color_str)
    magnitude = c.redF() + c.greenF() + c.blueF()
    if magnitude >= _TEXT_CONTRAST_THRESHOLD * 3:
        return QColor(Qt.GlobalColor.black)
    return QColor(Qt.GlobalColor.white)

def _traverse_upstream(node_item, visited=None):
    """
    Recursively collect all paths from any root to node_item.
    Returns a list of paths; each path is an ordered list of tuples:
        (BaseNodeItem, outgoing_port_name_or_None)
    where outgoing_port_name_or_None is the OUTPUT port name on THAT node
    leading to the NEXT node in the path (None for the final node in the path).
    """
    if visited is None:
        visited = frozenset()
    if node_item in visited:
        return [[(node_item, None)]]  # cycle guard
    visited = visited | {node_item}
    upstream = []  # list of (upstream_node_item, output_port_name_on_upstream_node)
    for sock in (node_item.inputs or []):
        for conn in sock.connections:
            if conn.socket_start and conn.socket_start.node_item:
                up_node = conn.socket_start.node_item
                # Determine which output port this connection came from
                out_port_name = None
                if hasattr(up_node, 'outputs'):
                    try:
                        out_idx = up_node.outputs.index(conn.socket_start)
                        nd = up_node.node_data
                        out_port_name = nd.output_ports.get(out_idx, "Default")
                    except (ValueError, AttributeError):
                        out_port_name = "Default"
                upstream.append((up_node, out_port_name))
    if not upstream:
        return [[(node_item, None)]]
    result = []
    for up_node, port_name in upstream:
        for path in _traverse_upstream(up_node, visited):
            # Replace the last tuple's port name with the outgoing port name
            new_path = path[:-1] + [(path[-1][0], port_name)] + [(node_item, None)]
            result.append(new_path)
    return result


class ConnectionItem(QGraphicsLineItem):
    def __init__(self, start_socket, end_socket=None):
        super().__init__()
        self.socket_start = start_socket
        self.socket_end = end_socket
        self.setZValue(5)
        self.line_color = "#646464"
        self.line_style = Qt.PenStyle.SolidLine
        self.setPen(QPen(QColor(self.line_color), 2, self.line_style))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

    def updatePath(self):
        if not self.socket_start:
            return
        p1 = self.socket_start.scenePos()
        if self.socket_end:
            p2 = self.socket_end.scenePos()
        else:
            p2 = self.last_pos if hasattr(self, 'last_pos') else p1
        
        self.setLine(QLineF(p1, p2))

    def shape(self):
        path = QPainterPath()
        line = self.line()
        if line.length() == 0:
            return path
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        path.moveTo(line.p1())
        path.lineTo(line.p2())
        return stroker.createStroke(path)

    def boundingRect(self):
        extra = 6
        line = self.line()
        return QRectF(line.p1(), line.p2()).normalized().adjusted(-extra, -extra, extra, extra)

    def paint(self, painter, option, widget=None):
        if self.isSelected():
            pen = QPen(QColor(255, 200, 50), 3, self.line_style)
        else:
            pen = QPen(QColor(self.line_color), 2, self.line_style)
        self.setPen(pen)
        super().paint(painter, option, widget)

class SocketItem(QGraphicsRectItem):
    def __init__(self, parent_node, is_input=True):
        size = 14  # default
        if parent_node and hasattr(parent_node, 'project_settings') and parent_node.project_settings:
            size = parent_node.project_settings.socket_size
        half = size // 2
        super().__init__(-half, -half, size, size, parent_node)
        self.node_item = parent_node
        self.is_input = is_input
        self.setBrush(QBrush(QColor(150, 150, 150)))
        self.setAcceptHoverEvents(True)
        self.setZValue(20) # Ensure sockets are on top
        self.connections = []
        self.label_item = None

    def apply_size(self, size):
        half = size // 2
        self.setRect(-half, -half, size, size)

    def scenePos(self):
        # Offset 4 pixels outward from the node edge so there's a gap between socket and node body
        rect = self.rect()
        center = rect.center()
        local = self.mapToScene(center)
        # Determine direction based on is_input and position relative to parent
        parent = self.parentItem()
        if parent:
            node_rect = parent.rect()
            node_cx = node_rect.x() + node_rect.width() / 2
            # parent-local position of socket center
            ploc = self.mapToParent(center)
            if self.is_input:
                # Input sockets are on the left edge — offset 4px further left
                offset_x = -4
            else:
                # Output sockets are on the right edge — offset 4px further right
                offset_x = 4
            adjusted_parent = ploc + type(ploc)(offset_x, 0)
            return parent.mapToScene(adjusted_parent)
        return local

class BaseNodeItem(QGraphicsRectItem):
    def __init__(self, node_data, x=0, y=0, project_settings=None):
        super().__init__(0, 0, 1, 1)  # placeholder; resize_for_type sets real size
        self.setPos(x, y)
        self.node_data = node_data
        self.project_settings = project_settings
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | 
                      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        
        self.title_text = QGraphicsTextItem(self.node_data.name, self)
        # Ensure text is well above background image
        self.title_text.setZValue(10)
        self.bg_image_item = None
        self.inputs = []
        self.outputs = []
        
        # Sockets created here
        self.resize_for_type()
        self.create_sockets()
        
        # Ensure the node itself is high enough so it doesn't get buried
        self.setZValue(1)
        self.update_appearance()

    def resize_for_type(self):
        """Resize the rect to the canonical size for the current NodeType."""
        from .models import NODE_SIZES, NodeType
        et = self.node_data.event_type
        w, h = NODE_SIZES.get(et, (150, 80))
        self.setRect(0, 0, w, h)

    def update_appearance(self):
        # Color based on type or subnetwork status
        color_str = "#505050" # Default
        if self.project_settings:
            if self.node_data.is_subnetwork:
                color_str = self.project_settings.node_colors.get("SUBNETWORK", "#417505")
            else:
                color_str = self.project_settings.node_colors.get(self.node_data.event_type.value, "#505050")
        
        base_color = QColor(color_str)
        # Apply semi-transparency if showing background image
        if self.node_data.image_path and self.node_data.show_bg_image:
            base_color.setAlpha(180)
            
        self.setBrush(QBrush(base_color))
        self.setPen(QPen(Qt.GlobalColor.white))
        # Cache text color so child label methods can reuse it without recomputing.
        self._node_text_color = _text_color_for_bg(color_str)
        self.title_text.setDefaultTextColor(self._node_text_color)
        self.title_text.setPlainText(self.node_data.name)

        # Position title text based on node shape
        from .models import NodeType as _ET
        from PyQt6.QtGui import QTextOption, QFont
        _r = self.rect()
        self.title_text.setTextWidth(_r.width() - 10)

        # Reset font to default before applying per-type overrides
        _base_font = QFont()
        if self.project_settings:
            _base_font.setPointSize(self.project_settings.font_size)
        self.title_text.setFont(_base_font)

        if self.node_data.event_type == _ET.CHARACTER:
            _char_font = QFont()
            _char_font.setPointSize(_base_font.pointSize() + 3)
            _char_font.setBold(True)
            self.title_text.setFont(_char_font)
            _th = self.title_text.boundingRect().height()
            self.title_text.setPos(5, (_r.height() - _th) / 2)
            self.title_text.document().setDefaultTextOption(QTextOption(Qt.AlignmentFlag.AlignCenter))
        elif self.node_data.event_type == _ET.GLOBALS:
            _th = self.title_text.boundingRect().height()
            self.title_text.setPos(5, (NODE_BAR_H - _th) / 2)
            self.title_text.document().setDefaultTextOption(QTextOption(Qt.AlignmentFlag.AlignLeft))
        elif self.node_data.is_subnetwork:
            _th = self.title_text.boundingRect().height()
            self.title_text.setPos(5, (NODE_BAR_H - _th) / 2)
            self.title_text.document().setDefaultTextOption(QTextOption(Qt.AlignmentFlag.AlignLeft))
        elif self.node_data.event_type in (_ET.START, _ET.END):
            _th = self.title_text.boundingRect().height()
            self.title_text.setPos(5, (_r.height() - _th) / 2)
            self.title_text.document().setDefaultTextOption(QTextOption(Qt.AlignmentFlag.AlignCenter))
        else:
            _th = self.title_text.boundingRect().height()
            self.title_text.setPos(5, 5)
            self.title_text.document().setDefaultTextOption(QTextOption(Qt.AlignmentFlag.AlignLeft))

        # DOT nodes are too small to show text
        self.title_text.setVisible(self.node_data.event_type != _ET.DOT)

        # --- Character labels for DIALOGUE/EVENT nodes ---
        self._update_character_labels()

        # --- Scene actions text for NOTE/INFO nodes ---
        self._update_actions_text()

        # --- GLOBALS variable labels ---
        self._update_globals_labels()

        # --- Port name labels (inputs/outputs rendered inside node body) ---
        self._update_port_labels()

        # Background image handle - scene-level item at Z=0 so it renders
        # behind all nodes (Z=1) without any extra iteration.
        if self.node_data.image_path and self.node_data.show_bg_image:
            if not self.bg_image_item:
                self.bg_image_item = QGraphicsPixmapItem()
                self.bg_image_item.setZValue(0)

            pixmap = QPixmap(self.node_data.image_path)
            if not pixmap.isNull():
                scale = self.project_settings.bg_image_scale if self.project_settings else 5.0
                target_w = self.rect().width() * scale
                target_h = self.rect().height() * scale
                pixmap = pixmap.scaled(int(target_w), int(target_h), Qt.AspectRatioMode.KeepAspectRatio)
                self.bg_image_item.setPixmap(pixmap)

            if self.scene() and not self.bg_image_item.scene():
                self.scene().addItem(self.bg_image_item)
            self._update_bg_image_pos()
        elif self.bg_image_item:
            if self.bg_image_item.scene():
                self.bg_image_item.scene().removeItem(self.bg_image_item)
            self.bg_image_item = None

    def _update_actions_text(self):
        from .models import NodeType as _ET
        if not hasattr(self, '_actions_text_item'):
            self._actions_text_item = None

        et = self.node_data.event_type
        if et not in (_ET.NOTE, _ET.INFO, _ET.EVENT):
            if self._actions_text_item and self._actions_text_item.scene():
                self._actions_text_item.scene().removeItem(self._actions_text_item)
                self._actions_text_item = None
            return

        text = self.node_data.scene_actions.strip()
        if not text:
            if self._actions_text_item and self._actions_text_item.scene():
                self._actions_text_item.scene().removeItem(self._actions_text_item)
                self._actions_text_item = None
            return

        if not self._actions_text_item:
            self._actions_text_item = QGraphicsTextItem(self)
            self._actions_text_item.setZValue(10)
        _afont = self._actions_text_item.font()
        _base_pt = self.project_settings.font_size if self.project_settings else _afont.pointSize()
        _afont.setPointSize(max(6, _base_pt - 1))
        self._actions_text_item.setFont(_afont)
        self._actions_text_item.setDefaultTextColor(
            getattr(self, '_node_text_color', QColor(Qt.GlobalColor.white))
        )

        PADDING = 4
        title_bottom = self.title_text.pos().y() + self.title_text.boundingRect().height()
        y = title_bottom + PADDING
        w = self.rect().width() - 10

        self._actions_text_item.setTextWidth(w)
        self._actions_text_item.setPlainText(text)
        self._actions_text_item.setPos(5, y)

        # Resize node to fit the wrapped text
        needed_h = y + self._actions_text_item.boundingRect().height() + PADDING
        current_rect = self.rect()
        if needed_h > current_rect.height():
            self.setRect(0, 0, current_rect.width(), needed_h)
            self._reposition_sockets()

    def _update_character_labels(self):
        from .models import NodeType as _ET
        # Remove previous character label items
        if not hasattr(self, '_char_label_items'):
            self._char_label_items = []
        for lbl in self._char_label_items:
            if lbl.scene():
                lbl.scene().removeItem(lbl)
        self._char_label_items = []

        et = self.node_data.event_type
        if et not in (_ET.DIALOGUE, _ET.EVENT):
            return

        chars = self.node_data.selected_characters
        if not chars:
            return

        LINE_H = 16   # px per character row
        PADDING = 4   # gap below title text
        title_bottom = self.title_text.pos().y() + self.title_text.boundingRect().height()
        y = title_bottom + PADDING

        # Resize node height to fit all labels if needed
        needed_h = y + len(chars) * LINE_H + PADDING
        current_rect = self.rect()
        if needed_h > current_rect.height():
            self.setRect(0, 0, current_rect.width(), needed_h)
            self._reposition_sockets()

        for name in chars:
            lbl = QGraphicsTextItem(f"  · {name}", self)
            lbl.setDefaultTextColor(
                getattr(self, '_node_text_color', QColor(Qt.GlobalColor.white))
            )
            lbl.setZValue(10)
            # Scale font slightly smaller than title
            font = lbl.font()
            _base_pt = self.project_settings.font_size if self.project_settings else font.pointSize()
            font.setPointSize(max(6, _base_pt - 1))
            lbl.setFont(font)
            lbl.setPos(5, y)
            y += LINE_H
            self._char_label_items.append(lbl)

    def _update_bg_image_pos(self):
        """Reposition bg_image_item in scene coords: centred on this node plus the global offset."""
        if not self.bg_image_item:
            return
        img_rect = self.bg_image_item.boundingRect()
        r = self.rect()
        ox = self.project_settings.bg_image_offset_x if self.project_settings else 0
        oy = self.project_settings.bg_image_offset_y if self.project_settings else 0
        self.bg_image_item.setPos(
            self.pos().x() + r.width() / 2 - img_rect.width() / 2 + ox,
            self.pos().y() + r.height() / 2 - img_rect.height() / 2 + oy,
        )

    def boundingRect(self):
        return self.rect().adjusted(-2, -2, 2, 2)

    def shape(self):
        from .models import NodeType
        r = self.rect()
        w, h = r.width(), r.height()
        path = QPainterPath()
        et = self.node_data.event_type
        if et == NodeType.START:
            # Backwards D: flat right wall, arc sweeps CW through left side
            path.moveTo(w, 0)
            path.lineTo(w, h)
            path.arcTo(QRectF(0, 0, 2 * w, h), 270, -180)
            path.closeSubpath()
        elif et == NodeType.END:
            # D shape: flat left wall, arc sweeps CCW through right side
            path.moveTo(0, 0)
            path.lineTo(0, h)
            path.arcTo(QRectF(-w, 0, 2 * w, h), 270, 180)
            path.closeSubpath()
        elif et == NodeType.DOT:
            path.addRoundedRect(r, 10, 10)
        else:
            path.addRect(r)
        return path

    def paint(self, painter, option, widget=None):
        from .models import NodeType
        r = self.rect()
        w, h = r.width(), r.height()
        et = self.node_data.event_type
        fill = self.brush()
        outline = QPen(QColor(255, 200, 50), 3) if self.isSelected() else QPen(Qt.GlobalColor.white, 1)
        painter.setPen(outline)
        painter.setBrush(fill)
        if et == NodeType.START:
            self._paint_backwards_d(painter, w, h)
        elif et == NodeType.END:
            self._paint_d(painter, w, h)
        elif et == NodeType.DOT:
            painter.drawRoundedRect(QRectF(0, 0, w, h), 10, 10)
        elif self.node_data.is_subnetwork:
            self._paint_mini_window(painter, w, h, fill, outline)
        elif et == NodeType.DIALOGUE:
            painter.drawRoundedRect(QRectF(0, 0, w, h), int(h*.25), int(h*.25))
        elif et == NodeType.GLOBALS:
            self._paint_globals(painter, w, h, fill, outline)
        else:
            painter.drawRect(QRectF(0, 0, w, h))

    def _paint_backwards_d(self, painter, w, h):
        """START: flat wall on right, semicircle curving to the left."""
        path = QPainterPath()
        path.moveTo(w, 0)
        path.lineTo(w, h)
        path.arcTo(QRectF(0, 0, 1.5 * w, h), 270, -180)
        path.closeSubpath()
        painter.drawPath(path)

    def _paint_d(self, painter, w, h):
        """END: flat wall on left, semicircle curving to the right."""
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(0, h)
        path.arcTo(QRectF(-0.5 * w, 0, 1.5 * w, h), 270, 180)
        path.closeSubpath()
        painter.drawPath(path)

    def _paint_mini_window(self, painter, w, h, fill, outline):
        """SUBNETWORK: rectangle body with a darker title bar strip at top."""
        # Body
        painter.drawRect(QRectF(0, 0, w, h))
        # Title bar fill
        bar_color = fill.color().darker(140)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bar_color))
        painter.drawRect(QRectF(0, 0, w, NODE_BAR_H))
        # Divider line and re-draw outer outline
        painter.setPen(outline)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QLineF(0, NODE_BAR_H, w, NODE_BAR_H))
        painter.drawRect(QRectF(0, 0, w, h))

    def _paint_globals(self, painter, w, h, fill, outline):
        """GLOBALS: rectangle body with a distinct title bar."""
        painter.drawRect(QRectF(0, 0, w, h))
        bar_color = QColor(60, 60, 140)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bar_color))
        painter.drawRect(QRectF(0, 0, w, NODE_BAR_H))
        painter.setPen(outline)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QLineF(0, NODE_BAR_H, w, NODE_BAR_H))
        painter.drawRect(QRectF(0, 0, w, h))

    def _update_globals_labels(self):
        from .models import NodeType as _ET, NODE_SIZES
        if not hasattr(self, '_globals_label_items'):
            self._globals_label_items = []
        for lbl in self._globals_label_items:
            if lbl.scene():
                lbl.scene().removeItem(lbl)
        self._globals_label_items = []
        if self.node_data.event_type != _ET.GLOBALS:
            return
        PADDING = 4
        LINE_H = 15
        y = NODE_BAR_H + PADDING
        for var_name, default_val in self.node_data.globals_vars.items():
            val_str = int(default_val) if isinstance(default_val, float) and default_val == int(default_val) else default_val
            lbl = QGraphicsTextItem(f"  {var_name} = {val_str}", self)
            lbl.setDefaultTextColor(getattr(self, '_node_text_color', QColor(Qt.GlobalColor.white)))
            lbl.setZValue(10)
            font = lbl.font()
            _base_pt = self.project_settings.font_size if self.project_settings else font.pointSize()
            font.setPointSize(max(6, _base_pt - 1))
            lbl.setFont(font)
            lbl.setPos(5, y)
            y += LINE_H
            self._globals_label_items.append(lbl)
        base_h = NODE_SIZES.get(_ET.GLOBALS, (220, 100))[1]
        needed_h = max(base_h, y + PADDING)
        current_rect = self.rect()
        if needed_h != current_rect.height():
            self.setRect(0, 0, current_rect.width(), needed_h)
            self._reposition_sockets()

    def _update_port_labels(self):
        """Render input and output port names as text rows at the bottom of the node body.

        Port names that are all 'Default' are skipped entirely so plain nodes stay
        compact.  When named ports exist the node height is grown to fit them and
        sockets are repositioned accordingly.
        """
        from .models import NodeType as _ET, NODE_SIZES

        # Clean up any previous port label items.
        if not hasattr(self, '_port_label_items'):
            self._port_label_items = []
        for lbl in self._port_label_items:
            if lbl.scene():
                lbl.scene().removeItem(lbl)
        self._port_label_items = []

        # DOT and GLOBALS nodes don't show port labels.
        et = self.node_data.event_type
        if et in (_ET.DOT, _ET.GLOBALS):
            return

        in_ports = self.node_data.input_ports or {0: "Default"}
        out_ports = self.node_data.output_ports or {0: "Default"}

        in_names = [in_ports[k] for k in sorted(in_ports.keys())]
        out_names = [out_ports[k] for k in sorted(out_ports.keys())]

        has_named_in = any(n != "Default" for n in in_names)
        has_named_out = any(n != "Default" for n in out_names)

        if not has_named_in and not has_named_out:
            return  # nothing to draw

        LINE_H = PORT_LABEL_FONT_SIZE + 4
        PADDING = 4
        # Number of rows = max of input vs output port counts (they sit side-by-side per row)
        max_rows = max(
            len(in_names) if has_named_in else 0,
            len(out_names) if has_named_out else 0,
        )
        extra_h = max_rows * LINE_H + PADDING * 2

        # Grow the node rect if needed to accommodate the label area.
        base_h = NODE_SIZES.get(et, (150, 80))[1]
        # Current rect height may already be grown by character/action labels;
        # port labels go below everything that's already there.
        current_rect = self.rect()
        # Mark where the port label zone starts (below existing content).
        # We use the existing rect height as the start of the port label zone,
        # but ensure it's at least base_h.
        zone_top = max(base_h, current_rect.height())
        needed_h = zone_top + extra_h
        if needed_h > current_rect.height():
            self.setRect(0, 0, current_rect.width(), needed_h)
            self._reposition_sockets()

        rect = self.rect()
        text_color = getattr(self, '_node_text_color', QColor(Qt.GlobalColor.white))

        def _make_label(text, x, y, align_right=False):
            lbl = QGraphicsTextItem(self)
            lbl.setDefaultTextColor(text_color)
            lbl.setZValue(10)
            from PyQt6.QtGui import QFont
            f = QFont()
            f.setPointSize(PORT_LABEL_FONT_SIZE)
            lbl.setFont(f)
            lbl.setPlainText(text)
            if align_right:
                lbl.setPos(rect.width() - lbl.boundingRect().width() - PADDING, y)
            else:
                lbl.setPos(PADDING, y)
            return lbl

        # Draw input port names on the left, output on the right, row by row.
        for row in range(max_rows):
            y = zone_top + PADDING + row * LINE_H
            if has_named_in and row < len(in_names):
                name = in_names[row]
                if name != "Default":
                    self._port_label_items.append(_make_label(f"↳ {name}", 0, y, align_right=False))
            if has_named_out and row < len(out_names):
                name = out_names[row]
                if name != "Default":
                    self._port_label_items.append(_make_label(f"{name} ↲", 0, y, align_right=True))

    def _reposition_sockets(self):
        """Reposition all input/output sockets evenly along the node edges based on current rect."""
        rect = self.rect()
        num_in = len(self.inputs)
        for i, sock in enumerate(self.inputs):
            if num_in == 1:
                sock.setPos(0, rect.height() / 2)
            else:
                sock.setPos(0, rect.height() * (i + 1) / (num_in + 1))
        if not self.node_data.is_subnetwork:
            num_out = len(self.outputs)
            for i, sock in enumerate(self.outputs):
                if num_out == 1:
                    sock.setPos(rect.width(), rect.height() / 2)
                else:
                    sock.setPos(rect.width(), rect.height() * (i + 1) / (num_out + 1))

    def get_subnet_meta(self):
        """Return runtime metadata dict about this node's subnetwork."""
        if not (self.node_data.is_subnetwork and self.node_data.subnetwork_id):
            return None
        sub = self.node_data.subnetwork_id
        end_count = 0
        characters = set()
        try:
            for item in sub.items():
                if type(item).__name__ == 'BaseNodeItem':
                    from .models import NodeType as _ET
                    if item.node_data.event_type == _ET.END:
                        end_count += 1
                    characters.update(getattr(item.node_data, 'selected_characters', []))
        except RuntimeError:
            pass
        return {'end_count': end_count, 'characters': sorted(characters)}

    def compute_paths(self):
        """Return a list of path strings from the graph root down to this node.
        DOT nodes are skipped so they don't clutter the path display.
        When an output port is named (not "Default"), it is appended as
        "Node; Output: PortName > NextNode"."""
        result = []
        for path in _traverse_upstream(self):
            segments = []
            for node_item, out_port in path:
                nd = node_item.node_data
                if nd.event_type.value == "Dot":
                    continue
                if out_port and out_port != "Default":
                    segments.append(f"{nd.name}; Output: {out_port}")
                else:
                    segments.append(nd.name)
            result.append(' > '.join(segments))
        return result

    def compute_variable_values(self, var_name, default_value=0.0):
        """
        Traverse upstream and compute all possible values of var_name at this node.
        Returns a deduplicated list of floats (one per unique upstream branch).
        """
        seen = []
        for path in _traverse_upstream(self):
            val = default_value
            for n, _port in path:
                nd = n.node_data
                if nd.variable_name == var_name:
                    op, delta = nd.variable_op, nd.variable_delta
                    if op == 'Set':
                        val = delta
                    elif op == 'Add':
                        val += delta
                    elif op == 'Subtract':
                        val -= delta
                    elif op == 'Multiply':
                        val *= delta
            if val not in seen:
                seen.append(val)
        return seen if seen else [default_value]

    def create_sockets(self):
        from .models import NodeType
        if not self.scene():
            return
            
        # Save existing connection info before clearing sockets
        old_input_conns = []
        if self.inputs:
            old_input_conns = [s.connections[:] for s in self.inputs]
        
        old_output_conns = []
        old_output_conns_by_name = {}
        if self.outputs:
            old_output_conns = [s.connections[:] for s in self.outputs]
            for sock in self.outputs:
                label = sock.label_item.toPlainText() if (hasattr(sock, 'label_item') and sock.label_item) else None
                if label is not None:
                    old_output_conns_by_name[label] = sock.connections[:]

        # Clear existing socket items AND their labels from the scene
        for sock in self.inputs + self.outputs:
            if hasattr(sock, 'label_item') and sock.label_item and self.scene():
                try:
                    self.scene().removeItem(sock.label_item)
                except RuntimeError:
                    pass
            if self.scene():
                try:
                    self.scene().removeItem(sock)
                except RuntimeError:
                    pass
        
        self.inputs = []
        self.outputs = []

        # Start nodes have no Inputs
        if self.node_data.event_type != NodeType.START:
            in_ports = self.node_data.input_ports
            # Ensure at least one port
            if not in_ports:
                in_ports = {0: "Default"}
            num_in = len(in_ports)
            rect = self.rect()
            # Spread sockets evenly along left edge
            for i, (idx, port_name) in enumerate(sorted(in_ports.items())):
                if num_in == 1:
                    y_pos = rect.height() / 2
                else:
                    y_pos = rect.height() * (i + 1) / (num_in + 1)
                in_sock = SocketItem(self, True)
                in_sock.setPos(0, y_pos)
                in_sock.label_item = None
                self.inputs.append(in_sock)
                # Re-attach old connections by index
                if i < len(old_input_conns):
                    for conn in old_input_conns[i]:
                        try:
                            conn.socket_end = in_sock
                            in_sock.connections.append(conn)
                        except RuntimeError:
                            pass
        
        # End nodes have no Outputs
        if self.node_data.event_type != NodeType.END:
            # Subnetworks have dynamic outputs based on End nodes in their scene
            if self.node_data.is_subnetwork and self.node_data.subnetwork_id:
                end_nodes = []
                # Safety check for scene validity
                try:
                    # reversed() gives oldest-first order so new End nodes
                    # always append to the bottom of the output list.
                    for item in reversed(list(self.node_data.subnetwork_id.items())):
                        # Direct check to avoid recursion/import issues
                        if type(item).__name__ == "BaseNodeItem" and item.node_data.event_type == NodeType.END:
                            end_nodes.append(item.node_data.name)
                except (RuntimeError, AttributeError):
                    pass
                
                # Update height if many outputs
                num_outs = max(1, len(end_nodes))
                new_h = max(100, num_outs * 30 + 30) # Extra buffer
                self.setRect(0, 0, 150, new_h)
                if self.inputs:
                    for j, in_sock in enumerate(self.inputs):
                        in_sock.setPos(0, new_h * (j + 1) / (len(self.inputs) + 1))

                for i, name in enumerate(end_nodes):
                    out_sock = SocketItem(self, False)
                    y_pos = 40 + i * 30
                    out_sock.setPos(self.rect().width(), y_pos)
                    self.outputs.append(out_sock)

                    # Re-attach by name first, then fall back to old index
                    conns_to_restore = (old_output_conns_by_name.get(name)
                                        or (old_output_conns[i] if i < len(old_output_conns) else []))
                    for conn in conns_to_restore:
                        try:
                            conn.socket_start = out_sock
                            out_sock.connections.append(conn)
                        except RuntimeError:
                            pass

                    # Add label for socket
                    lbl = QGraphicsTextItem(name, self)
                    lbl.setDefaultTextColor(
                        getattr(self, '_node_text_color', QColor(Qt.GlobalColor.white))
                    )
                    lbl.setZValue(10)
                    lbl.setPos(self.rect().width() - lbl.boundingRect().width() - 10, y_pos - 10)
                    out_sock.label_item = lbl # Store to remove later
            else:
                out_ports = self.node_data.output_ports
                if not out_ports:
                    out_ports = {0: "Default"}
                num_out = len(out_ports)
                rect = self.rect()
                for i, (idx, port_name) in enumerate(sorted(out_ports.items())):
                    if num_out == 1:
                        y_pos = rect.height() / 2
                    else:
                        y_pos = rect.height() * (i + 1) / (num_out + 1)
                    out_sock = SocketItem(self, False)
                    out_sock.setPos(rect.width(), y_pos)
                    out_sock.label_item = None
                    self.outputs.append(out_sock)
                    # Re-attach old connections by name first, then by index
                    conns_to_restore = (old_output_conns_by_name.get(port_name)
                                        or (old_output_conns[i] if i < len(old_output_conns) else []))
                    for conn in conns_to_restore:
                        try:
                            conn.socket_start = out_sock
                            out_sock.connections.append(conn)
                        except RuntimeError:
                            pass
        
        # Finally, trigger path updates for all re-attached connections
        for sock in self.inputs + self.outputs:
            for conn in sock.connections:
                try:
                    conn.updatePath()
                except RuntimeError:
                    pass

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for sock in self.inputs + self.outputs:
                for conn in sock.connections:
                    conn.updatePath()
            self._update_bg_image_pos()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged:
            new_scene = self.scene()
            if new_scene:
                # Node just entered a scene - register any pending bg_image_item
                if self.bg_image_item and not self.bg_image_item.scene():
                    new_scene.addItem(self.bg_image_item)
                    self._update_bg_image_pos()
            else:
                # Node left the scene - clean up the detached bg_image_item
                if self.bg_image_item and self.bg_image_item.scene():
                    self.bg_image_item.scene().removeItem(self.bg_image_item)
                self.bg_image_item = None
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        # Triggered by view to handle subnetwork entry
        super().mouseDoubleClickEvent(event)
