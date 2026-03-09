from PyQt6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsItem, 
                             QGraphicsRectItem, QGraphicsLineItem, QGraphicsPixmapItem,
                             QGraphicsTextItem)
from PyQt6.QtCore import Qt, QPointF, QLineF, QRectF
from PyQt6.QtGui import QPen, QBrush, QColor, QRadialGradient, QPixmap, QPainterPath, QPainterPathStroker

NODE_BAR_H = 20  # Title bar height for the SUBNETWORK mini-window shape

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
        super().__init__(-7, -7, 14, 14, parent_node)
        self.node_item = parent_node
        self.is_input = is_input
        self.setBrush(QBrush(QColor(150, 150, 150)))
        self.setAcceptHoverEvents(True)
        self.setZValue(20) # Ensure sockets are on top
        self.connections = []
        self.label_item = None

    def scenePos(self):
        return self.mapToScene(self.rect().center())

class BaseNodeItem(QGraphicsRectItem):
    def __init__(self, node_data, x=0, y=0, project_settings=None):
        from models import EventType
        _et = node_data.event_type
        if _et in (EventType.START, EventType.END):
            _w, _h = 100, 64
        elif _et == EventType.DIALOGUE:
            _w, _h = 150, 50
        else:
            _w, _h = 150, 80
        super().__init__(0, 0, _w, _h)
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
        self.create_sockets()
        
        # Ensure the node itself is high enough so it doesn't get buried
        self.setZValue(1)
        self.update_appearance()

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
        self.title_text.setPlainText(self.node_data.name)

        # Position title text based on node shape
        from models import EventType as _ET
        from PyQt6.QtGui import QTextOption
        _r = self.rect()
        self.title_text.setTextWidth(_r.width() - 10)
        _th = self.title_text.boundingRect().height()
        if self.node_data.is_subnetwork:
            self.title_text.setPos(5, (NODE_BAR_H - _th) / 2)
            self.title_text.document().setDefaultTextOption(QTextOption(Qt.AlignmentFlag.AlignLeft))
        elif self.node_data.event_type in (_ET.START, _ET.END):
            self.title_text.setPos(5, (_r.height() - _th) / 2)
            self.title_text.document().setDefaultTextOption(QTextOption(Qt.AlignmentFlag.AlignCenter))
        else:
            self.title_text.setPos(5, 5)
            self.title_text.document().setDefaultTextOption(QTextOption(Qt.AlignmentFlag.AlignLeft))

        # Background image handle
        if self.node_data.image_path and self.node_data.show_bg_image:
            if not self.bg_image_item:
                self.bg_image_item = QGraphicsPixmapItem(self)
                # Set VERY low ZValue to be behind EVERYTHING 
                self.bg_image_item.setZValue(-100)
                # Ensure it doesn't inherit parent flag transformations in a weird way
                self.bg_image_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent, True)
            
            pixmap = QPixmap(self.node_data.image_path)
            if not pixmap.isNull():
                scale = self.project_settings.bg_image_scale if self.project_settings else 5.0
                target_w = self.rect().width() * scale
                target_h = self.rect().height() * scale
                pixmap = pixmap.scaled(int(target_w), int(target_h), Qt.AspectRatioMode.KeepAspectRatio)
                self.bg_image_item.setPixmap(pixmap)
                # Centering
                img_rect = self.bg_image_item.boundingRect()
                self.bg_image_item.setPos(self.rect().width()/2 - img_rect.width()/2, 
                                          self.rect().height()/2 - img_rect.height()/2)
        elif self.bg_image_item:
            self.bg_image_item.setParentItem(None)
            if self.scene():
                self.scene().removeItem(self.bg_image_item)
            self.bg_image_item = None

    def boundingRect(self):
        return self.rect().adjusted(-2, -2, 2, 2)

    def shape(self):
        from models import EventType
        r = self.rect()
        w, h = r.width(), r.height()
        path = QPainterPath()
        et = self.node_data.event_type
        if et == EventType.START:
            # Backwards D: flat right wall, arc sweeps CW through left side
            path.moveTo(w, 0)
            path.lineTo(w, h)
            path.arcTo(QRectF(0, 0, 2 * w, h), 270, -180)
            path.closeSubpath()
        elif et == EventType.END:
            # D shape: flat left wall, arc sweeps CCW through right side
            path.moveTo(0, 0)
            path.lineTo(0, h)
            path.arcTo(QRectF(-w, 0, 2 * w, h), 270, 180)
            path.closeSubpath()
        else:
            path.addRect(r)
        return path

    def paint(self, painter, option, widget=None):
        from models import EventType
        r = self.rect()
        w, h = r.width(), r.height()
        et = self.node_data.event_type
        fill = self.brush()
        outline = QPen(QColor(255, 200, 50), 3) if self.isSelected() else QPen(Qt.GlobalColor.white, 1)
        painter.setPen(outline)
        painter.setBrush(fill)
        if et == EventType.START:
            self._paint_backwards_d(painter, w, h)
        elif et == EventType.END:
            self._paint_d(painter, w, h)
        elif self.node_data.is_subnetwork:
            self._paint_mini_window(painter, w, h, fill, outline)
        elif et == EventType.DIALOGUE:
            painter.drawRoundedRect(QRectF(0, 0, w, h), int(h*.25), int(h*.25))
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

    def create_sockets(self):
        from models import EventType
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
        if self.node_data.event_type != EventType.START:
            in_sock = SocketItem(self, True)
            in_sock.setPos(0, self.rect().height() / 2)
            self.inputs.append(in_sock)
            # Re-attach old connections if it was an input-providing node
            if old_input_conns and len(old_input_conns) > 0:
                for conn in old_input_conns[0]:
                    try:
                        conn.socket_end = in_sock
                        in_sock.connections.append(conn)
                    except RuntimeError:
                        pass
        
        # End nodes have no Outputs
        if self.node_data.event_type != EventType.END:
            # Subnetworks have dynamic outputs based on End nodes in their scene
            if self.node_data.is_subnetwork and self.node_data.subnetwork_id:
                end_nodes = []
                # Safety check for scene validity
                try:
                    # reversed() gives oldest-first order so new End nodes
                    # always append to the bottom of the output list.
                    for item in reversed(list(self.node_data.subnetwork_id.items())):
                        # Direct check to avoid recursion/import issues
                        if type(item).__name__ == "BaseNodeItem" and item.node_data.event_type == EventType.END:
                            end_nodes.append(item.node_data.name)
                except (RuntimeError, AttributeError):
                    pass
                
                # Update height if many outputs
                num_outs = max(1, len(end_nodes))
                new_h = max(100, num_outs * 30 + 30) # Extra buffer
                self.setRect(0, 0, 150, new_h)
                if self.inputs:
                    self.inputs[0].setPos(0, new_h / 2)

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
                    lbl.setDefaultTextColor(Qt.GlobalColor.white)
                    lbl.setZValue(10)
                    lbl.setPos(self.rect().width() - lbl.boundingRect().width() - 10, y_pos - 10)
                    out_sock.label_item = lbl # Store to remove later
            else:
                out_sock = SocketItem(self, False)
                out_sock.setPos(self.rect().width(), self.rect().height() / 2)
                self.outputs.append(out_sock)
                # Re-attach old output connections
                if old_output_conns and len(old_output_conns) > 0:
                    for conn in old_output_conns[0]:
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
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        # Triggered by view to handle subnetwork entry
        super().mouseDoubleClickEvent(event)
