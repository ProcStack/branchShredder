from PyQt6.QtWidgets import (QMainWindow, QGraphicsView, QGraphicsScene, 
                             QWidget, QHBoxLayout, QVBoxLayout, 
                             QToolBar, QMessageBox, 
                             QApplication, QFileDialog,
                             QSplitter, QSizePolicy, QRubberBand,
                             QProgressBar, QLabel)
from PyQt6.QtCore import Qt, QPointF, QRect, QSize, QTimer, QUrl
from PyQt6.QtGui import QAction, QPainter, QColor, QPen, QPalette

import os
from .models import NodeData, NodeType, ProjectSettings
from .graph_items import BaseNodeItem, ConnectionItem, SocketItem
from .widgets import NodeInspector, SettingsSidebar, StoryWritingBar, ConnectionInspector
from .ai_widgets import AIPromptBar

from .manager import ProjectManager, AppSettingsManager
from .ai_manager import AIManager
from .markdown_renderer import MarkdownRenderer
from .ws_client import BranchShredderWSClient, _MainThreadBridge

scriptName = "branchShredder"
scriptTitle = "Branch Shredder"
scriptVersion = "0.4"

class StatusMessageType:
    NONE = -1
    OPEN = 0
    INFO = 1
    ERROR = 2
    SUCCESS = 3

_STATUS_COLORS = {
    StatusMessageType.NONE:    "#aaaaaa",
    StatusMessageType.OPEN:    "#83c1ff",
    StatusMessageType.INFO:    "#aaaaaa",
    StatusMessageType.ERROR:   "#de5c5c",
    StatusMessageType.SUCCESS: "#78ee8f",
}

class GraphScene(QGraphicsScene):
    
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setBackgroundBrush(QColor(30,30,30))
        # Parent Scene Track
        self.parent_scene = None
        self.name = "Root"

    def mouseDoubleClickEvent(self, event):
        # Coordinates in scenePos() are already correct for adding nodes
        item = self.itemAt(event.scenePos(), self.views()[0].transform())
        # If double click on empty space, add node
        if not item:
            self.add_node(event.scenePos().x(), event.scenePos().y())
        super().mouseDoubleClickEvent(event)

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)

        if not self.settings.show_grid:
            return

        GRID_MINOR = self.settings.grid_minor
        GRID_MAJOR = self.settings.grid_major

        minor_pen = QPen(QColor(34, 34, 34), 0)   # 0 = cosmetic 1px regardless of zoom
        major_pen = QPen(QColor(50, 50, 50), 0)

        # Snap rect outward so lines always start off-screen.
        left   = int(rect.left())   - (int(rect.left())   % GRID_MINOR)
        top    = int(rect.top())    - (int(rect.top())    % GRID_MINOR)
        right  = int(rect.right())  + GRID_MINOR
        bottom = int(rect.bottom()) + GRID_MINOR

        # Minor lines - step exactly by GRID_MINOR
        painter.setPen(minor_pen)
        x = left
        while x <= right:
            painter.drawLine(x, top, x, bottom)
            x += GRID_MINOR
        y = top
        while y <= bottom:
            painter.drawLine(left, y, right, y)
            y += GRID_MINOR

        # Major lines drawn on top - step exactly by GRID_MAJOR
        # (independent of GRID_MINOR so spacing is always correct)
        major_left = int(rect.left()) - (int(rect.left()) % GRID_MAJOR)
        major_top  = int(rect.top())  - (int(rect.top())  % GRID_MAJOR)
        painter.setPen(major_pen)
        x = major_left
        while x <= right:
            painter.drawLine(x, top, x, bottom)
            x += GRID_MAJOR
        y = major_top
        while y <= bottom:
            painter.drawLine(left, y, right, y)
            y += GRID_MAJOR

    def add_node(self, x, y, data=None):
        if not data:
            data = NodeData()
        node_item = BaseNodeItem(data, x, y, self.settings)
        self.addItem(node_item)
        node_item.create_sockets()
        
        # Notify if scene has a callback (for subnetworks)
        if hasattr(self, 'itemAddedOrRemoved'):
            self.itemAddedOrRemoved()
        return node_item

    def create_connection(self, socket_start, socket_end):
        # Normalize: socket_start must be the output, socket_end the input
        if socket_start.is_input:
            socket_start, socket_end = socket_end, socket_start
        # Reject self-connections
        if socket_start.node_item is socket_end.node_item:
            return
        # Check if connection already exists
        for conn in socket_start.connections:
            if conn.socket_end == socket_end or conn.socket_start == socket_end:
                return
        
        new_conn = ConnectionItem(socket_start, socket_end)
        self.addItem(new_conn)
        socket_start.connections.append(new_conn)
        socket_end.connections.append(new_conn)
        new_conn.updatePath()
        return new_conn

class GraphView(QGraphicsView):
    def __init__(self, scene, settings, parent=None):
        self._selection_handler = None
        super().__init__(scene, parent)
        self.settings = settings
        self.setRenderHints(QPainter.RenderHint.Antialiasing | 
                           QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._dragging = False
        self._last_mouse_pos = QPointF()
        self._current_connection = None
        self._drag_node = None
        self._drag_start_pos = None
        self._rubber_band = None
        self._rubber_band_origin = None
        self.setAcceptDrops(True)

    def setScene(self, scene):
        old = self.scene()
        if old and self._selection_handler:
            try:
                old.selectionChanged.disconnect(self._selection_handler)
            except (TypeError, RuntimeError):
                pass
        super().setScene(scene)
        if scene and self._selection_handler:
            scene.selectionChanged.connect(self._selection_handler)

    def _remove_connection(self, conn):
        if conn.socket_start and conn in conn.socket_start.connections:
            conn.socket_start.connections.remove(conn)
        if conn.socket_end and conn in conn.socket_end.connections:
            conn.socket_end.connections.remove(conn)
        if conn.scene():
            conn.scene().removeItem(conn)

    def start_connection(self, socket):
        self._current_connection = ConnectionItem(socket)
        self.scene().addItem(self._current_connection)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            shift_held = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            items = self.items(event.pos())

            if shift_held:
                # Shift+Click on a node: toggle it in/out of the selection.
                for item in items:
                    temp = item
                    while temp and not isinstance(temp, BaseNodeItem):
                        temp = temp.parentItem()
                    if isinstance(temp, BaseNodeItem):
                        temp.setSelected(not temp.isSelected())
                        return
                # Shift+drag on empty space: start rubber-band area select.
                self._rubber_band_origin = event.pos()
                if self._rubber_band is None:
                    self._rubber_band = QRubberBand(
                        QRubberBand.Shape.Rectangle, self.viewport()
                    )
                self._rubber_band.setGeometry(
                    QRect(self._rubber_band_origin, QSize(0, 0))
                )
                self._rubber_band.show()
                return

            found_socket = None
            for item in items:
                temp = item
                while temp and not isinstance(temp, SocketItem):
                    temp = temp.parentItem()
                if isinstance(temp, SocketItem):
                    found_socket = temp
                    break
            
            if found_socket:
                # Input with existing connections: reconnect mode
                if found_socket.is_input and found_socket.connections:
                    conn = found_socket.connections[-1]
                    other_socket = conn.socket_start
                    self._remove_connection(conn)
                    if other_socket:
                        self.start_connection(other_socket)
                else:
                    self.start_connection(found_socket)
                return
            
            # Track node for potential drop-on-curve
            self._drag_node = None
            self._drag_start_pos = None
            for item in items:
                temp = item
                while temp and not isinstance(temp, BaseNodeItem):
                    temp = temp.parentItem()
                if isinstance(temp, BaseNodeItem):
                    self._drag_node = temp
                    self._drag_start_pos = QPointF(temp.pos())
                    break
            
            if not items:
                self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
                self._dragging = True
        elif event.button() == Qt.MouseButton.RightButton:
            self._right_click_zoom = True
            self._last_mouse_pos = event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._current_connection:
            # Check for socket at release point
            found_socket = None
            items = self.items(event.pos())
            for item in items:
                temp = item
                while temp and not isinstance(temp, SocketItem):
                    temp = temp.parentItem()
                if isinstance(temp, SocketItem):
                    # Check if it's a valid target
                    if (temp.node_item != self._current_connection.socket_start.node_item and
                        temp.is_input != self._current_connection.socket_start.is_input):
                        found_socket = temp
                        break
            
            if found_socket:
                # Normalize: ensure socket_start is always the output
                start_sock = self._current_connection.socket_start
                end_sock = found_socket
                if start_sock.is_input:
                    start_sock, end_sock = end_sock, start_sock
                self._current_connection.socket_start = start_sock
                self._current_connection.socket_end = end_sock
                self._current_connection.updatePath()
                # Finalize connection lists
                start_sock.connections.append(self._current_connection)
                end_sock.connections.append(self._current_connection)
                self._current_connection = None
            else:
                # Check if dropped onto a node body - connect to its first compatible socket
                origin_socket = self._current_connection.socket_start
                found_node = None
                for item in items:
                    temp = item
                    while temp and not isinstance(temp, BaseNodeItem):
                        temp = temp.parentItem()
                    if isinstance(temp, BaseNodeItem) and temp is not origin_socket.node_item:
                        found_node = temp
                        break

                if found_node:
                    # Find first compatible socket on the target node
                    target_socket = None
                    if not origin_socket.is_input:
                        # origin is output → target needs an input
                        target_socket = found_node.inputs[0] if found_node.inputs else None
                    else:
                        # origin is input → target needs an output
                        target_socket = found_node.outputs[0] if found_node.outputs else None

                    if target_socket:
                        # Normalize: ensure socket_start is always the output
                        if origin_socket.is_input:
                            self._current_connection.socket_start = target_socket
                            self._current_connection.socket_end = origin_socket
                        else:
                            self._current_connection.socket_end = target_socket
                        self._current_connection.updatePath()
                        origin_socket.connections.append(self._current_connection)
                        target_socket.connections.append(self._current_connection)
                        self._current_connection = None
                    else:
                        self.scene().removeItem(self._current_connection)
                        self._current_connection = None
                else:
                    # Maybe spawn a new node at the drop position
                    self.scene().removeItem(self._current_connection)
                    self._current_connection = None
                    if self.settings.create_node_on_empty_drop:
                        drop_scene_pos = self.mapToScene(event.pos())
                        new_data = NodeData()
                        new_node = self.scene().add_node(
                            drop_scene_pos.x(), drop_scene_pos.y(), new_data
                        )
                        # Connect origin output → new node input, or input → new node output
                        if not origin_socket.is_input and new_node.inputs:
                            self.scene().create_connection(origin_socket, new_node.inputs[0])
                        elif origin_socket.is_input and new_node.outputs:
                            self.scene().create_connection(new_node.outputs[0], origin_socket)

        # Check for drop-on-curve insertion
        if (event.button() == Qt.MouseButton.LeftButton and
            self._drag_node and self._drag_start_pos):
            node = self._drag_node
            delta = node.pos() - self._drag_start_pos
            if abs(delta.x()) > 1 or abs(delta.y()) > 1:
                # Node was moved - check if it landed on a connection
                if node.inputs and node.outputs and not node.inputs[0].connections:
                    for item in list(self.scene().items()):
                        if (isinstance(item, ConnectionItem) and item.socket_end and
                            node.collidesWithItem(item)):
                            old_start = item.socket_start
                            old_end = item.socket_end
                            # Skip if this connection belongs to the node itself
                            if (old_start.node_item is node or old_end.node_item is node):
                                break
                            self._remove_connection(item)
                            self.scene().create_connection(old_start, node.inputs[0])
                            self.scene().create_connection(node.outputs[0], old_end)
                            break
            self._drag_node = None
            self._drag_start_pos = None

        if self._rubber_band and self._rubber_band.isVisible():
            sel_rect = QRect(self._rubber_band_origin, event.pos()).normalized()
            scene_rect = self.mapToScene(sel_rect).boundingRect()
            for item in self.scene().items(scene_rect):
                temp = item
                while temp and not isinstance(temp, BaseNodeItem):
                    temp = temp.parentItem()
                if isinstance(temp, BaseNodeItem):
                    temp.setSelected(True)
            self._rubber_band.hide()
            self._rubber_band_origin = None
            return

        if self._dragging:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self._dragging = False
        
        # Reset zoom lock regardless of where release happens
        if event.button() == Qt.MouseButton.RightButton:
            self._right_click_zoom = False
        
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            selected = self.scene().selectedItems()
            for item in selected:
                if isinstance(item, ConnectionItem):
                    self._remove_connection(item)
            # Delegate node deletion to main window
            remaining = [i for i in self.scene().selectedItems() if isinstance(i, BaseNodeItem)]
            if remaining:
                main_win = self.window()
                if hasattr(main_win, 'delete_selected_node'):
                    main_win.delete_selected_node()
            return
        elif event.key() == Qt.Key.Key_Y:
            selected = self.scene().selectedItems()
            for item in selected:
                if isinstance(item, BaseNodeItem):
                    for sock in item.inputs + item.outputs:
                        for conn in sock.connections[:]:
                            self._remove_connection(conn)
            return
        elif event.key() == Qt.Key.Key_U:
            main_win = self.window()
            if hasattr(main_win, 'exit_subnet_scene'):
                main_win.exit_subnet_scene()
            return
        elif event.key() == Qt.Key.Key_I:
            selected = self.scene().selectedItems()
            for item in selected:
                if isinstance(item, BaseNodeItem):
                    self.handle_node_double_click(item)
                    break
            return
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        if self._current_connection:
            self._current_connection.last_pos = self.mapToScene(event.pos())
            self._current_connection.updatePath()

        if self._rubber_band and self._rubber_band.isVisible():
            self._rubber_band.setGeometry(
                QRect(self._rubber_band_origin, event.pos()).normalized()
            )

        if hasattr(self, '_right_click_zoom') and self._right_click_zoom:
            diffX = event.pos().x() - self._last_mouse_pos.x()
            diffY = -event.pos().y() + self._last_mouse_pos.y()
            diff = diffX if abs(diffX) > abs(diffY) else diffY
            factor = 1.001 ** diff
            self.scale(factor, factor)
            self._last_mouse_pos = event.pos()
        super().mouseMoveEvent(event)

    _IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif'}

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    ext = os.path.splitext(url.toLocalFile())[1].lower()
                    if ext in self._IMAGE_EXTENSIONS:
                        event.acceptProposedAction()
                        return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    ext = os.path.splitext(url.toLocalFile())[1].lower()
                    if ext in self._IMAGE_EXTENSIONS:
                        event.acceptProposedAction()
                        return
        event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    ext = os.path.splitext(url.toLocalFile())[1].lower()
                    if ext in self._IMAGE_EXTENSIONS:
                        image_path = url.toLocalFile()
                        scene_pos = self.mapToScene(event.position().toPoint())
                        node_data = NodeData(os.path.splitext(os.path.basename(image_path))[0])
                        node_data.image_path = image_path
                        node_data.show_bg_image = True
                        self.scene().add_node(scene_pos.x(), scene_pos.y(), node_data)
                        event.acceptProposedAction()
                        return
        event.ignore()

    def mouseDoubleClickEvent(self, event):
        item = self.itemAt(event.pos())

        # Double-click on a connection → insert a Dot node
        if isinstance(item, ConnectionItem) and item.socket_end:
            scene_pos = self.mapToScene(event.pos())
            self._insert_dot_on_connection(item, scene_pos)
            return

        # Traverse up to find BaseNodeItem if double clicked on label/image
        temp = item
        while temp and not isinstance(temp, BaseNodeItem):
            temp = temp.parentItem()
        if isinstance(temp, BaseNodeItem):
            self.handle_node_double_click(temp)
        else:
            super().mouseDoubleClickEvent(event)

    def _insert_dot_on_connection(self, conn_item, scene_pos):
        old_start = conn_item.socket_start
        old_end = conn_item.socket_end
        self._remove_connection(conn_item)
        dot_data = NodeData("", NodeType.DOT)
        dot_node = self.scene().add_node(scene_pos.x() - 15, scene_pos.y() - 15, dot_data)
        if dot_node.inputs and dot_node.outputs:
            self.scene().create_connection(old_start, dot_node.inputs[0])
            self.scene().create_connection(dot_node.outputs[0], old_end)

    def handle_node_double_click(self, node_item):
        if not node_item.node_data.is_subnetwork:
            res = QMessageBox.question(self, "Subnetwork", 
                                     "Do you want to turn this node into a subnetwork?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if res == QMessageBox.StandardButton.Yes:
                self.enter_subnetwork(node_item)
        else:
            self.enter_subnetwork(node_item)

    def enter_subnetwork(self, node_item):
        if not node_item.node_data.subnetwork_id:
            new_scene = GraphScene(self.settings)
            new_scene.parent_scene = self.scene()
            new_scene.name = node_item.node_data.name
            node_item.node_data.subnetwork_id = new_scene
            node_item.node_data.is_subnetwork = True

            # Add default START/END first, before wiring the callback.
            # This prevents create_sockets() from firing mid-setup when outputs
            # is already cleared (START node added) but no End nodes exist yet,
            # which would cause the original output connections to be dropped.
            in_data = NodeData("Start", NodeType.START)
            out_data = NodeData("End", NodeType.END)
            new_scene.add_node(100, 300, in_data)
            new_scene.add_node(600, 300, out_data)

            # Now do a single create_sockets() pass. old_output_conns is still
            # intact from the pre-conversion outputs, so existing connections
            # get properly re-attached to the new output socket.
            node_item.create_sockets()

            # Watch for future end-node count changes in the subnetwork
            new_scene.itemAddedOrRemoved = lambda: node_item.create_sockets()

            node_item.update_appearance()

        self.setScene(node_item.node_data.subnetwork_id)

    # ------------------------------------------------------------------
    # Viewport capture & remote-control helpers
    # ------------------------------------------------------------------

    def capture_viewport_png(self, width: int = None, height: int = None) -> bytes:
        """Grab the current viewport and return it as PNG bytes.

        Optionally rescale to *width* × *height* (aspect ratio preserved).
        """
        from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
        pixmap = self.grab()
        if width or height:
            w = width or pixmap.width()
            h = height or pixmap.height()
            pixmap = pixmap.scaled(
                w, h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buf, "PNG")
        buf.close()
        return bytes(ba)

    def get_viewport_state(self) -> dict:
        """Return the current viewport centre (scene coords) and zoom factor.

        Returns a dict with keys ``x``, ``y`` (scene-coordinate centre of the
        visible area) and ``zoom`` (the current uniform scale factor, where
        ``1.0`` is the default 1:1 zoom).
        """
        center = self.mapToScene(self.viewport().rect().center())
        zoom = self.transform().m11()   # uniform scale; m11 == m22 for all our transforms
        vp = self.viewport()
        return {
            "x": center.x(),
            "y": center.y(),
            "zoom": zoom,
            "pixelWidth": vp.width(),
            "pixelHeight": vp.height(),
        }

    def pan_scene(self, dx: float, dy: float):
        """Pan the viewport by (*dx*, *dy*) scene-coordinate units."""
        center = self.mapToScene(self.viewport().rect().center())
        self.centerOn(center.x() + dx, center.y() + dy)

    def tap_at_image_coords(self, tap_x: float, tap_y: float,
                             image_width: int, image_height: int):
        """Select the topmost node at the tapped image-pixel position.

        Scales *tap_x* / *tap_y* (pixel coordinates within the delivered
        image) back to viewport widget space using the ratio
        ``image / viewport``, then converts to scene coordinates and
        hit-tests the scene.

        The matching node is selected (triggering the normal
        ``selectionChanged`` signal so the inspector / sidebar update).

        Returns a node-data dict if a node was found, or ``None`` if the
        tap landed on empty space.
        """
        from .graph_items import BaseNodeItem

        vp = self.viewport()
        vp_w = vp.width()
        vp_h = vp.height()

        # Map image-pixel → viewport-widget pixel
        vp_x = tap_x * vp_w / image_width
        vp_y = tap_y * vp_h / image_height

        # Clamp to valid viewport bounds
        vp_x = max(0.0, min(vp_x, float(vp_w - 1)))
        vp_y = max(0.0, min(vp_y, float(vp_h - 1)))

        scene_pos = self.mapToScene(int(vp_x), int(vp_y))

        # Hit-test: find the topmost BaseNodeItem at this scene position
        node_item = None
        for item in self.scene().items(scene_pos):
            temp = item
            while temp and not isinstance(temp, BaseNodeItem):
                temp = temp.parentItem()
            if isinstance(temp, BaseNodeItem):
                node_item = temp
                break

        # Update selection — triggers selectionChanged → on_selection_changed
        self.scene().clearSelection()
        if node_item:
            node_item.setSelected(True)
            nd = node_item.node_data
            return {
                "nodeId": nd.id,
                "name": nd.name,
                "type": nd.event_type.value,
                "content": nd.markdown_content,
                "stageNotes": nd.stage_notes,
                "selectedCharacters": nd.selected_characters,
            }
        return None

    def zoom_by_factor(self, factor: float):
        """Multiply the current zoom level by *factor* (e.g. 0.98 = zoom out 2%)."""
        if factor > 0:
            self.scale(factor, factor)

    def center_on_node_id(self, node_id: str) -> bool:
        """Center the viewport on the node whose ``id`` matches *node_id*.

        Searches the current scene tree (including subnetworks).
        Returns ``True`` on success, ``False`` if the node was not found.
        """
        scene = self.scene()
        if not scene:
            return False

        seen: set = set()

        def _walk(sc):
            for item in sc.items():
                if not isinstance(item, BaseNodeItem):
                    continue
                nd = item.node_data
                if nd.id in seen:
                    continue
                seen.add(nd.id)
                if nd.id == node_id:
                    return item
                if nd.is_subnetwork and nd.subnetwork_id:
                    found = _walk(nd.subnetwork_id)
                    if found:
                        return found
            return None

        node_item = _walk(scene)
        if node_item:
            self.centerOn(node_item)
            return True
        return False

    def apply_viewport_commands(self, commands: list):
        """Execute a pipeline of viewport commands.

        Each element in *commands* is a dict whose keys name operations and
        whose values are the operation arguments.  Operations are applied in
        list order; within a single dict, keys are processed in insertion
        order.

        Supported keys (case-insensitive):
            Move          [dx, dy]  — pan by scene-coordinate offset
            zoom          factor    — multiply current zoom by factor
            center        [x, y]   — center on absolute scene position
            center_node   nodeId   — center on a node by its ID
            viewport      "Render" — capture PNG snapshot
            output        "WebSocket" — where to deliver the image (metadata)
            width         pixels   — output image width for next Render
            height        pixels   — output image height for next Render

        Always returns a 2-tuple ``(png_bytes | None, viewport_state)``.
        ``png_bytes`` is only set when a ``viewport: Render`` command is
        encountered; ``viewport_state`` is always populated with the final
        ``x``, ``y``, and ``zoom`` values after all commands have run.
        """
        render_width: int = None
        render_height: int = None

        for step in commands:
            if not isinstance(step, dict):
                continue
            for key, value in step.items():
                k = key.lower()
                if k == "move":
                    if isinstance(value, (list, tuple)) and len(value) >= 2:
                        self.pan_scene(float(value[0]), float(value[1]))
                elif k == "zoom":
                    self.zoom_by_factor(float(value))
                elif k == "center":
                    if isinstance(value, (list, tuple)) and len(value) >= 2:
                        self.centerOn(float(value[0]), float(value[1]))
                elif k == "center_node":
                    self.center_on_node_id(str(value))
                elif k == "width":
                    render_width = int(value)
                elif k == "height":
                    render_height = int(value)
                elif k == "viewport":
                    if str(value).lower() == "render":
                        png = self.capture_viewport_png(render_width, render_height)
                        return (png, self.get_viewport_state())
                elif k == "output":
                    pass  # only "WebSocket" is currently supported; kept for protocol compat
                elif k == "_reset_zoom":
                    # Internal: reset transform to identity before applying absolute zoom.
                    self.resetTransform()
        return (None, self.get_viewport_state())

class MainWindow(QMainWindow):
    def __init__(self, autoBoot = True):
        super().__init__()
        self.project_manager = ProjectManager()
        self.app_settings = AppSettingsManager()

        if autoBoot:
          self.boot()

    def boot(self):
        title = f"{scriptTitle} v{scriptVersion}"
        self.setWindowTitle( title )
        self.resize( 1200, 800 )
        
        self.settings = ProjectSettings()
        self.ai_manager = AIManager()
        
        # Main vertical splitter (Graph on top, Story on bottom)
        self.v_splitter = QSplitter(Qt.Orientation.Vertical)
        self.v_splitter.setHandleWidth(5)
        self.v_splitter.setStyleSheet("""
            QSplitter::handle {
                background: #4a4a4a;
                margin: 0px;
            }
            QSplitter::handle:hover {
                background: #787878;
            }
            QSplitter::handle:pressed {
                background: #999999;
            }
        """)
        self.setCentralWidget(self.v_splitter)

        # Top Area: Graph + Sidebar
        self.top_container = QWidget()
        self.top_layout = QHBoxLayout(self.top_container)
        self.top_layout.setContentsMargins(0, 0, 0, 0)
        
        # Central Graph
        self.scene = GraphScene(self.settings)
        self._populate_default_scene(self.scene)
        self.view = GraphView(self.scene, self.settings)
        self.top_layout.addWidget(self.view)
        
        # Sidebar Stack (Inspector + Settings)
        self.sidebar_container = QWidget()
        self.sidebar_container.setFixedWidth(300)
        self.sidebar_layout = QVBoxLayout(self.sidebar_container)
        
        self.inspector = NodeInspector()
        self.inspector.nodeChanged.connect(self.on_node_changed)
        self.inspector.portsChanged.connect(self.on_ports_changed)
        
        self.connection_inspector = ConnectionInspector()
        self.connection_inspector.hide()
        
        self.settings_sidebar = SettingsSidebar(self.settings)
        self.settings_sidebar.settingsChanged.connect(self.on_settings_changed)
        self.settings_sidebar.hide()
        
        self.sidebar_layout.addWidget(self.inspector)
        self.sidebar_layout.addWidget(self.connection_inspector)
        self.sidebar_layout.addWidget(self.settings_sidebar)
        self.top_layout.addWidget(self.sidebar_container)
        
        # Bottom Area: Story Writing Bar
        self.story_bar = StoryWritingBar()

        # Bottom Area: AI Prompt Bar
        self.ai_bar = AIPromptBar(self.ai_manager, self.settings,
                                  scene_getter=lambda: self.view.scene())

        self.v_splitter.addWidget(self.top_container)
        self.v_splitter.addWidget(self.story_bar)
        self.v_splitter.addWidget(self.ai_bar)
        self.v_splitter.setStretchFactor(0, 3)
        self.v_splitter.setStretchFactor(1, 1)
        self.v_splitter.setStretchFactor(2, 1)
        self.ai_bar.setVisible(self.settings.show_ai_bar)
        
        self.view._selection_handler = self.on_selection_changed
        self.view.setScene(self.scene)
        
        self.create_menu()
        self.create_toolbar()
        self._setup_status_bar()

        # procMessenger WebSocket client
        self._ws_bridge = _MainThreadBridge()
        self._ws_bridge.start()
        self._ws_client: BranchShredderWSClient | None = None
        self._start_ws_client()


    # ------------------------------------------------------------------
    # Status bar helpers
    # ------------------------------------------------------------------


    def _setup_status_bar(self):
        sb = self.statusBar()
        sb.setStyleSheet("""
            QStatusBar {
                background: #353535;
                color: #aaaaaa;
                border-top: 1px solid #4e4e4e;
                font-size: 9pt;
            }
            QStatusBar::item { border: none; }
        """)

        # Custom label so we can set per-message colours
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #aaaaaa; padding: 0 4px;")
        sb.addWidget(self._status_label)

        # Single-shot timer to auto-clear the label
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(lambda: self._status_label.setText(""))

        self._status_progress = QProgressBar()
        self._status_progress.setRange(0, 0)   # indeterminate busy indicator
        self._status_progress.setTextVisible(False)
        self._status_progress.setMaximumWidth(160)
        self._status_progress.setMaximumHeight(14)
        self._status_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #666666;
                border-radius: 3px;
                background: #464646;
            }
            QProgressBar::chunk {
                background: #5a9fd4;
                border-radius: 2px;
            }
        """)
        self._status_progress.hide()
        sb.addPermanentWidget(self._status_progress)

    def show_status(self, msg: str, duration_ms: int = 5000, type: int = StatusMessageType.NONE):
        """Display a timed, coloured message in the status bar."""
        color = _STATUS_COLORS.get(type, "#aaaaaa")
        self._status_label.setStyleSheet(f"color: {color}; padding: 0 4px;")
        self._status_label.setText(msg)
        self._status_timer.start(duration_ms)

    def _set_download_active(self, msg: str):
        """Show a persistent download status with an indeterminate progress bar."""
        self._status_timer.stop()
        color = _STATUS_COLORS.get(StatusMessageType.OPEN, "#83c1ff")
        self._status_label.setStyleSheet(f"color: {color}; padding: 0 4px;")
        self._status_label.setText(msg)
        self._status_progress.show()

    def _set_download_done(self, msg: str):
        """Hide the progress bar and show a timed completion/error message."""
        self._status_progress.hide()
        is_error = msg.lower().startswith("download error")
        stype = StatusMessageType.ERROR if is_error else StatusMessageType.SUCCESS
        self.show_status(msg, 5000, stype)

    # ------------------------------------------------------------------
    # procMessenger WebSocket helpers
    # ------------------------------------------------------------------

    def _start_ws_client(self):
        """Read .env and start (or restart) the WS client if enabled."""
        env = self.ai_manager._env
        enabled = env.get("PROC_MESSENGER_ENABLED", "false").lower() in ("1", "true", "yes")
        if not enabled:
            return

        host = env.get("PROC_MESSENGER_HOST", "192.168.1.154")
        port_str = env.get("PROC_MESSENGER_PORT", "9734")
        client_name = env.get("PROC_MESSENGER_CLIENT_NAME", "branchShredder")
        try:
            port = int(port_str)
        except ValueError:
            port = 9734

        # Stop any existing client first
        self._stop_ws_client()

        self._ws_client = BranchShredderWSClient(
            host=host,
            port=port,
            client_name=client_name,
            scene_getter=lambda: self.view.scene(),
            settings_getter=lambda: self.settings,
            ai_manager=self.ai_manager,
            bridge=self._ws_bridge,
            app_settings_getter=lambda: self.app_settings,
            open_project_fn=self._open_recent,
            new_project_fn=self.new_project,
            save_project_fn=self._ws_save_project,
            project_root=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            view_getter=lambda: self.view,
        )
        self._ws_client.start()
        self.show_status(
            f"procMessenger: connecting to {host}:{port}…",
            4000,
            StatusMessageType.INFO,
        )

    def _stop_ws_client(self):
        if self._ws_client:
            self._ws_client.stop()
            self._ws_client = None

    def _ws_save_project(self, path: str | None):
        """Save helper called from the WebSocket thread via the Qt bridge.

        If *path* is None the current project path is used (in-place save).
        If the project has never been saved and no path is given this is a
        no-op (the ws_client layer already validates the filename before
        calling here).
        """
        if path:
            self.project_manager.save_project_as(path, self.scene, self.settings)
            self.app_settings.add_recent(path)
            self._rebuild_recent_menu()
            self.show_status(f"Saved: {os.path.basename(path)}")
        elif self.project_manager and self.project_manager.current_project_path:
            self.project_manager.save_project(self.scene, self.settings)
            self.show_status(
                f"Saved: {os.path.basename(self.project_manager.current_project_path)}"
            )

    def closeEvent(self, event):
        self._stop_ws_client()
        if hasattr(self, "_ws_bridge"):
            self._ws_bridge.stop()
        super().closeEvent(event)

    # ------------------------------------------------------------------

    def keyPressEvent(self, event):
        isControl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        isShift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if event.key() == Qt.Key.Key_S and isShift and isControl:
            self.save_project_as()
            return
        elif event.key() == Qt.Key.Key_S and isControl:
            self.save_project()
            return
        
        super().keyPressEvent(event)


    def get_all_character_names(self):
        # Gather names from all CHARACTER-type nodes in the current scene and all parent scenes
        names = []
        scene = self.view.scene()
        while scene:
            for item in scene.items():
                if isinstance(item, BaseNodeItem) and item.node_data.event_type == NodeType.CHARACTER:
                    name = item.node_data.name.strip()
                    if name:
                        names.append(name)
            scene = getattr(scene, 'parent_scene', None)
        return sorted(set(names))

    def get_network_variables(self):
        """Collect all variables declared by GLOBALS nodes in the current and parent scenes."""
        vars_dict = {}
        scene = self.view.scene()
        while scene:
            for item in scene.items():
                if isinstance(item, BaseNodeItem) and item.node_data.event_type == NodeType.GLOBALS:
                    vars_dict.update(item.node_data.globals_vars)
            scene = getattr(scene, 'parent_scene', None)
        return vars_dict

    def create_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        file_menu.setStyleSheet("QMenu::separator { height: 6px; margin: 0px; }")

        new_act = QAction("&New Project", self)
        new_act.triggered.connect(self.new_project)
        file_menu.addAction(new_act)

        file_menu.addSeparator()

        load_act = QAction("&Open Project", self)
        load_act.triggered.connect(self.load_project)
        file_menu.addAction(load_act)

        self.recent_menu = file_menu.addMenu("Open &Recent")
        self._rebuild_recent_menu()

        file_menu.addSeparator()

        save_as_act = QAction("&Save As...", self)
        save_as_act.triggered.connect(self.save_project_as)
        file_menu.addAction(save_as_act)

        save_act = QAction("&Save Project", self)
        save_act.triggered.connect(self.save_project)
        file_menu.addAction(save_act)

        file_menu.addSeparator()

        quit_act = QAction("&Quit", self)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        # -- -- --

        shortcut_menu = menubar.addMenu("&Help...")
        shortcuts = {
            "Move Nodes" : "Left Click + Drag Node",
            "Pan Scene" : "Left Click + Drag Empty Area",
            "Zoom Scene" : "Right Click + Drag",
            "Create Node" : "Left Click -or- Drag line out from a Socket & Release",
            "Select Node / Connection Line" : "Left Click",
            "Select Multiple Nodes" : "Shift + Left Click -or- Shift + Drag Empty Area",
            "Delete Selected Node/Connection" : "Delete Key",
            "Reconnect" : "Click+Drag on Connected Socket",
            "Disconnect all connections on selected node" : "Press `Y`",
            "Insert Dot on Connection" : "Double Click on Connection Line",
            "Insert Node on Connection" : "Drag+Drop Node onto Connection Line",
            "Create / Enter Subnetwork" : "Double Click on Node -or- Click 'Create/Enter Subnet' -or- Press 'I'",
            "Exit Subnetwork" : "Click 'Exit Subnet' -or- Press 'U'",
            "Nova AI" : "Enable in Project Settings, shows at bottom of window"
        }

        
        for action, shortcut in shortcuts.items():
            act = QAction(f"{action} -- {shortcut}", self)
            act.setEnabled(False)
            shortcut_menu.addAction(act)


    def create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        toolbar.setStyleSheet("""
            QToolButton {
                color: #dddddd;
                background: transparent;
                border: none;
                padding: 4px 8px;
            }
            QToolButton:hover {
                background: #505050;
                border-radius: 4px;
            }
            QToolButton:pressed {
                background: #3e3e3e;
                border-radius: 4px;
            }
        """)
        
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        
        self.add_node_act = QAction("Add Node", self)
        self.add_node_act.triggered.connect(lambda: self.view.scene().add_node(0,0))
        toolbar.addAction(self.add_node_act)
        
        self.del_node_act = QAction("Delete Node", self)
        self.del_node_act.triggered.connect(self.delete_selected_node)
        toolbar.addAction(self.del_node_act)


        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        spacer.setMaximumWidth(100)
        toolbar.addWidget(spacer)


        self.enter_subnet_act = QAction("Create/Enter Subnet", self)
        self.enter_subnet_act.triggered.connect(self.enter_selected_subnet)
        toolbar.addAction(self.enter_subnet_act)

        self.back_act = QAction("Exit Subnet", self)
        self.back_act.triggered.connect(self.exit_subnet_scene)
        toolbar.addAction(self.back_act)


        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        spacer.setMaximumWidth(100)
        toolbar.addWidget(spacer)


        self.settings_act = QAction("Project Settings", self)
        self.settings_act.triggered.connect(self.toggle_settings_sidebar)
        toolbar.addAction(self.settings_act)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        spacer.setFixedWidth(8)
        toolbar.addWidget(spacer)

        self.font_dec_act = QAction("A−", self)
        self.font_dec_act.setToolTip("Decrease text size")
        self.font_dec_act.triggered.connect(lambda: self.adjust_font_size(-1))
        toolbar.addAction(self.font_dec_act)

        self.font_inc_act = QAction("A+", self)
        self.font_inc_act.setToolTip("Increase text size")
        self.font_inc_act.triggered.connect(lambda: self.adjust_font_size(1))
        toolbar.addAction(self.font_inc_act)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

    def adjust_font_size(self, delta):
        new_size = max(7, min(24, self.settings.font_size + delta))
        if new_size == self.settings.font_size:
            return
        self.settings.font_size = new_size
        # Scale the application-wide UI font so sidebars/labels follow along
        app = QApplication.instance()
        app_font = app.font()
        app_font.setPointSize(new_size)
        app.setFont(app_font)
        # Keep the markdown renderer in sync
        MarkdownRenderer.set_font_size(new_size)
        # Update text editor widgets directly (QApplication.setFont won't
        # retroactively resize existing QTextEdit documents)
        from PyQt6.QtGui import QFont as _QFont
        _ef = _QFont()
        _ef.setPointSize(new_size)
        for widget in (
            self.story_bar.text_editor,
            self.story_bar.stage_notes,
            self.ai_bar.prompt_input,
        ):
            widget.setFont(_ef)
        # Re-render any visible markdown HTML so font size takes effect immediately
        self.ai_bar.refresh_font()
        if self.story_bar.preview_browser.isVisible():
            self.story_bar._update_preview()
        # Refresh all node appearances
        self.on_settings_changed()
        self.show_status(f"Text size: {new_size}pt")

    def toggle_settings_sidebar(self):
        if self.settings_sidebar.isHidden():
            self.settings_sidebar.show()
            self.inspector.hide()
            self.connection_inspector.hide()
        else:
            self.settings_sidebar.hide()
            self.inspector.show()

    def on_selection_changed(self):
        items = self.view.scene().selectedItems()
        node_items = [i for i in items if isinstance(i, BaseNodeItem)]
        conn_item = next((i for i in items if isinstance(i, ConnectionItem)), None)

        if len(node_items) > 1:
            # Multiple nodes selected - clear the inspector so nothing is editable
            self.inspector.set_node(None)
            self.story_bar.set_node(None, [])
            self._selected_item = None
            self.settings_sidebar.hide()
            self.connection_inspector.hide()
            self.inspector.show()
            return

        node_item = node_items[0] if node_items else None

        if node_item:
            node_data = node_item.node_data
            self.inspector.set_node(node_data, node_item)
            self.inspector.set_network_variables(self.get_network_variables())
            self.inspector.set_available_characters(self.get_all_character_names())
            self._selected_item = node_item
            self._last_event_type = node_data.event_type
            
            # Update story bar with character list from parents
            self.story_bar.set_node(node_data, self.get_all_character_names())

            # Ensure inspector is shown when selecting node
            self.settings_sidebar.hide()
            self.connection_inspector.hide()
            self.inspector.show()
        elif conn_item:
            self.connection_inspector.set_connection(conn_item)
            self.inspector.set_node(None)
            self.story_bar.set_node(None, [])
            self._selected_item = None
            
            self.settings_sidebar.hide()
            self.inspector.hide()
            self.connection_inspector.show()
        else:
            self.inspector.set_node(None)
            self.connection_inspector.set_connection(None)
            self.connection_inspector.hide()
            self.story_bar.set_node(None, [])

    def on_node_changed(self):
        if hasattr(self, '_selected_item') and self._selected_item:
            try:
                if self._selected_item.scene() is None:
                    self._selected_item = None
                    return

                current_type = self._selected_item.node_data.event_type
                type_changed = getattr(self, '_last_event_type', None) != current_type

                # Resize BEFORE update_appearance so text placement reads the correct rect
                if type_changed:
                    self._selected_item.resize_for_type()
                    self._last_event_type = current_type

                self._selected_item.update_appearance()

                # Recreate sockets after resize so socket positions are correct
                if type_changed:
                    self._selected_item.create_sockets()

                # Refresh available character list in case type changed to/from Dialogue/Event
                if type_changed:
                    self.inspector.set_available_characters(self.get_all_character_names())
                # Refresh variable list (GLOBALS node may have changed; type change may affect panels)
                self.inspector.set_network_variables(self.get_network_variables())

                # If we renamed an END node inside a subnetwork, the parent needs to update labels
                scene = self.view.scene()
                if hasattr(scene, 'itemAddedOrRemoved'):
                    scene.itemAddedOrRemoved()
                # Keep the story bar node name label in sync with renames
                self.story_bar.node_name_lbl.setText(self._selected_item.node_data.name)
            except RuntimeError:
                self._selected_item = None

    def on_ports_changed(self):
        """Called when the user adds/removes/renames a port in the inspector.
        Recreates sockets on the selected node to match the new port configuration."""
        if hasattr(self, '_selected_item') and self._selected_item:
            try:
                if self._selected_item.scene() is None:
                    return
                self._selected_item.create_sockets()
                self._selected_item.update_appearance()
            except RuntimeError:
                pass

    def on_settings_changed(self):
        # Update all nodes in current scene
        for item in self.view.scene().items():
            if isinstance(item, BaseNodeItem):
                item.update_appearance()
                # Resize all sockets to match new socket_size setting
                for sock in item.inputs + item.outputs:
                    sock.apply_size(self.settings.socket_size)
        # Redraw background (grid visibility/spacing may have changed)
        self.view.scene().update()
        # Show/hide AI bar and refresh model list when visibility or keys may have changed
        self.ai_bar.setVisible(self.settings.show_ai_bar)
        if self.settings.show_ai_bar:
            self.ai_bar.refresh_models()

    def delete_selected_node(self):
        items = self.view.scene().selectedItems()
        if not items: return
        
        res = QMessageBox.question(self, "Delete", "Delete node?", 
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if res == QMessageBox.StandardButton.Yes:
            scene = self.view.scene()
            for item in items:
                if isinstance(item, BaseNodeItem):
                    # Collect all upstream source sockets and downstream dest sockets
                    sources = []
                    dests = []
                    for sock in item.inputs:
                        for conn in sock.connections:
                            src = conn.socket_start if conn.socket_end == sock else conn.socket_end
                            if src:
                                sources.append(src)
                    for sock in item.outputs:
                        for conn in sock.connections:
                            dst = conn.socket_end if conn.socket_start == sock else conn.socket_start
                            if dst:
                                dests.append(dst)

                    # Remove every connection attached to this node
                    for sock in item.inputs + item.outputs:
                        for conn in sock.connections[:]:
                            self.view._remove_connection(conn)

                    # Bypass: reconnect upstream → downstream only when both exist
                    if len(sources) == 1 and len(dests) == 1:
                        self.view.scene().create_connection(sources[0], dests[0])

                    self.view.scene().removeItem(item)
                elif isinstance(item, ConnectionItem):
                    self.view._remove_connection(item)
            
            # Notify for subnetwork updates
            if hasattr(scene, 'itemAddedOrRemoved'):
                scene.itemAddedOrRemoved()

    def exit_subnet_scene(self):
        curr = self.view.scene()
        if curr.parent_scene:
            self.view.setScene(curr.parent_scene)

    def enter_selected_subnet(self):
        scene = self.view.scene()
        selected_nodes = [i for i in scene.selectedItems() if isinstance(i, BaseNodeItem)]
        if len(selected_nodes) > 1:
            self._collapse_multi_to_subnet(selected_nodes)
            return
        # Single-node: original behavior
        for item in scene.selectedItems():
            if isinstance(item, BaseNodeItem):
                self.view.handle_node_double_click(item)
                break

    def _collapse_multi_to_subnet(self, selected_nodes):
        """Collapse multiple selected nodes into a new subnet, replacing them in
        the parent with a single SUBNETWORK node.

        - External incoming connections → a START node wired to the receiving nodes.
        - Each external outgoing connection → a named END node ("<source node name> End")
          wired from the outgoing node inside the subnet.
        - The subnet node in the parent is re-wired to match all outgoing END nodes.
        """
        scene = self.view.scene()

        res = QMessageBox.question(
            self, "Create Subnetwork",
            f"Collapse {len(selected_nodes)} selected nodes into a new subnetwork?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res != QMessageBox.StandardButton.Yes:
            return

        selected_id_set = {id(n) for n in selected_nodes}

        # --- 1. Catalog connections by stable (node, index) pairs ---
        # Using node-object + socket index so references survive create_sockets() rebuilds.
        seen_conn_ids: set = set()
        internal_connections = []  # (src_node, src_out_idx, dst_node, dst_in_idx)
        external_incoming = []     # (parent_src_socket, dst_node_in_sel, dst_in_idx)
        external_outgoing = []     # (src_node_in_sel, src_out_idx, parent_dst_socket)

        for node in selected_nodes:
            for in_idx, sock in enumerate(node.inputs):
                for conn in list(sock.connections):
                    if id(conn) in seen_conn_ids:
                        continue
                    if not conn.socket_start or not conn.socket_end:
                        continue
                    seen_conn_ids.add(id(conn))
                    src_node = conn.socket_start.node_item
                    try:
                        src_out_idx = src_node.outputs.index(conn.socket_start)
                    except ValueError:
                        src_out_idx = 0
                    if id(src_node) in selected_id_set:
                        internal_connections.append((src_node, src_out_idx, node, in_idx))
                    else:
                        external_incoming.append((conn.socket_start, node, in_idx))

            for out_idx, sock in enumerate(node.outputs):
                for conn in list(sock.connections):
                    if id(conn) in seen_conn_ids:
                        continue
                    if not conn.socket_start or not conn.socket_end:
                        continue
                    seen_conn_ids.add(id(conn))
                    dst_node = conn.socket_end.node_item
                    try:
                        dst_in_idx = dst_node.inputs.index(conn.socket_end)
                    except ValueError:
                        dst_in_idx = 0
                    if id(dst_node) not in selected_id_set:
                        external_outgoing.append((node, out_idx, conn.socket_end))
                    else:
                        # Capture here directly — the input scan will skip it
                        # because it's already in seen_conn_ids.
                        internal_connections.append((node, out_idx, dst_node, dst_in_idx))

        # --- 2. Remove every connection touching the selected nodes ---
        all_conns: set = set()
        for node in selected_nodes:
            for sock in node.inputs + node.outputs:
                for conn in sock.connections:
                    all_conns.add(conn)
        for conn in all_conns:
            self.view._remove_connection(conn)

        # --- 3. Layout metrics (in parent scene coords, before move) ---
        center_x   = sum(n.pos().x() + n.rect().width()  / 2 for n in selected_nodes) / len(selected_nodes)
        center_y   = sum(n.pos().y() + n.rect().height() / 2 for n in selected_nodes) / len(selected_nodes)
        min_x      = min(n.pos().x()                         for n in selected_nodes)
        min_y      = min(n.pos().y()                         for n in selected_nodes)
        max_x_edge = max(n.pos().x() + n.rect().width()      for n in selected_nodes)

        # Translate so the cluster's top-left corner lands at (250, 200) inside the subnet.
        offset_x = 250 - min_x
        offset_y = 200 - min_y

        # --- 4. Create the new subnet scene ---
        new_scene = GraphScene(self.settings)
        new_scene.parent_scene = scene
        new_scene.name = selected_nodes[0].node_data.name

        # --- 5. Move selected nodes into the new scene ---
        # Qt supports transferring items between scenes via removeItem / addItem.
        # Child SocketItems travel with their parent BaseNodeItem automatically.
        for node in selected_nodes:
            old_pos = node.pos()
            scene.removeItem(node)
            node.setPos(old_pos.x() + offset_x, old_pos.y() + offset_y)
            new_scene.addItem(node)
            node.create_sockets()  # re-register sockets in the new scene context

        # --- 6. Re-create internal connections inside the subnet ---
        for (src_node, src_idx, dst_node, dst_in_idx) in internal_connections:
            if src_idx < len(src_node.outputs) and dst_in_idx < len(dst_node.inputs):
                new_scene.create_connection(
                    src_node.outputs[src_idx], dst_node.inputs[dst_in_idx]
                )

        # --- 7. START node — centred vertically on the moved cluster ---
        avg_cy = sum(n.pos().y() + n.rect().height() / 2 for n in selected_nodes) / len(selected_nodes)
        start_node = new_scene.add_node(80, avg_cy - 20, NodeData("Start", NodeType.START))

        # Wire START → each distinct internal node that had an external input
        connected_to_start: set = set()
        for (_, dst_node, dst_in_idx) in external_incoming:
            if id(dst_node) not in connected_to_start:
                connected_to_start.add(id(dst_node))
                if start_node.outputs and dst_in_idx < len(dst_node.inputs):
                    new_scene.create_connection(
                        start_node.outputs[0], dst_node.inputs[dst_in_idx]
                    )

        # --- 8. END nodes — one per unique external destination node ---
        # Group connections by destination node so that multiple selected nodes
        # all pointing to the same outside node share one End node.
        _seen_dst: dict = {}
        grouped_outgoing = []
        for (src_node, src_out_idx, parent_dst_sock) in external_outgoing:
            key = id(parent_dst_sock.node_item)
            if key not in _seen_dst:
                _seen_dst[key] = len(grouped_outgoing)
                grouped_outgoing.append({'dst_node': parent_dst_sock.node_item, 'entries': []})
            grouped_outgoing[_seen_dst[key]]['entries'].append((src_node, src_out_idx, parent_dst_sock))

        end_x = max_x_edge + offset_x + 150
        for i, group in enumerate(grouped_outgoing):
            entries = group['entries']
            # Single-source: name after the source node; multi-source: name after the destination.
            if len(entries) == 1:
                end_name = f"{entries[0][0].node_data.name} End"
            else:
                end_name = f"{group['dst_node'].node_data.name} End"
            end_node = new_scene.add_node(end_x, 200 + i * 90, NodeData(end_name, NodeType.END))
            for (src_node, src_out_idx, _) in entries:
                if src_out_idx < len(src_node.outputs) and end_node.inputs:
                    new_scene.create_connection(src_node.outputs[src_out_idx], end_node.inputs[0])

        # Fallback: if no external outgoing, place a plain END so the subnet isn't empty.
        if not external_outgoing:
            new_scene.add_node(end_x, avg_cy - 20, NodeData("End", NodeType.END))

        # --- 9. Create SUBNETWORK node in the parent ---
        subnet_data = NodeData(new_scene.name, NodeType.NOTE)
        subnet_item = scene.add_node(center_x - 75, center_y - 50, subnet_data)
        subnet_item.node_data.is_subnetwork = True
        subnet_item.node_data.subnetwork_id = new_scene
        new_scene.itemAddedOrRemoved = lambda: subnet_item.create_sockets()
        subnet_item.create_sockets()
        subnet_item.update_appearance()
        if hasattr(scene, 'itemAddedOrRemoved'):
            scene.itemAddedOrRemoved()

        # --- 10. Re-wire parent connections to/from the subnet node ---
        # External incoming sources → subnet input socket
        seen_src_socks: set = set()
        for (parent_src_sock, _, _) in external_incoming:
            if id(parent_src_sock) not in seen_src_socks:
                seen_src_socks.add(id(parent_src_sock))
                if subnet_item.inputs:
                    scene.create_connection(parent_src_sock, subnet_item.inputs[0])

        # Subnet outputs → external outgoing targets (output order mirrors grouped END node order)
        for i, group in enumerate(grouped_outgoing):
            if i < len(subnet_item.outputs):
                seen_dst_socks: set = set()
                for (_, _, parent_dst_sock) in group['entries']:
                    if id(parent_dst_sock) not in seen_dst_socks:
                        seen_dst_socks.add(id(parent_dst_sock))
                        scene.create_connection(subnet_item.outputs[i], parent_dst_sock)

        # --- 11. Enter the new subnet ---
        self.view.setScene(new_scene)

    def _populate_default_scene(self, scene):
        """Add an unconnected Start node (left) and End node (right) to a blank scene."""
        scene.add_node(100, 300, NodeData("Start", NodeType.START))
        scene.add_node(600, 300, NodeData("End", NodeType.END))

    def new_project(self):
        self.settings = ProjectSettings()
        new_scene = GraphScene(self.settings)
        self._populate_default_scene(new_scene)
        self.view.setScene(new_scene)
        self.inspector.set_node(None)
        self.ai_bar.setVisible(self.settings.show_ai_bar)
        self.show_status("New project created.")
        
    # ------------------------------------------------------------------
    # Recent projects helpers
    # ------------------------------------------------------------------

    def _rebuild_recent_menu(self):
        self.recent_menu.clear()
        recent = self.app_settings.recent_projects
        if recent:
            for path in recent:
                act = QAction(os.path.basename(path), self)
                act.setToolTip(path)
                act.triggered.connect(lambda checked, p=path: self._open_recent(p))
                self.recent_menu.addAction(act)
        else:
            empty_act = QAction("(no recent projects)", self)
            empty_act.setEnabled(False)
            self.recent_menu.addAction(empty_act)
        self.recent_menu.addSeparator()
        clear_act = QAction("Clear Recent List", self)
        clear_act.triggered.connect(self._clear_recent)
        self.recent_menu.addAction(clear_act)

    def _open_recent(self, path):
        if not os.path.exists(path):
            QMessageBox.warning(self, "File Not Found", f"Project not found:\n{path}")
            self.app_settings.remove_recent(path)
            self._rebuild_recent_menu()
            return
        root_data = self.project_manager.load_project(path, self.settings)
        new_scene = GraphScene(self.settings)
        self.reconstruct_scene(new_scene, root_data)
        self.view.setScene(new_scene)
        self.scene = new_scene
        self.settings_sidebar.refresh()
        self.ai_bar.setVisible(self.settings.show_ai_bar)
        app = QApplication.instance()
        app_font = app.font()
        app_font.setPointSize(self.settings.font_size)
        app.setFont(app_font)
        MarkdownRenderer.set_font_size(self.settings.font_size)
        self.app_settings.add_recent(path)
        self._rebuild_recent_menu()
        self.show_status(f"Opened: {os.path.basename(path)}", type=StatusMessageType.OPEN)

    def _clear_recent(self):
        self.app_settings.clear_recent()
        self._rebuild_recent_menu()

    # ------------------------------------------------------------------

    def save_project_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "JSON Files (*.json)")
        if path:
            self.project_manager.save_project_as( path, self.scene, self.settings )
            self.app_settings.add_recent(path)
            self._rebuild_recent_menu()
            self.show_status(f"Saved: {os.path.basename(path)}")
    
    def save_project(self):
        if self.project_manager and self.project_manager.current_project_path:
            self.project_manager.save_project( self.scene, self.settings )
            self.show_status(f"Saved: {os.path.basename(self.project_manager.current_project_path)}")
        else:
            self.save_project_as()
            
    def load_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "JSON Files (*.json)")
        if path:
            root_data = self.project_manager.load_project(path, self.settings)
            # Basic reconstruction for root:
            new_scene = GraphScene(self.settings)
            self.reconstruct_scene(new_scene, root_data)
            self.view.setScene(new_scene)
            self.scene = new_scene # Update main ref
            self.settings_sidebar.refresh()
            self.ai_bar.setVisible(self.settings.show_ai_bar)
            # Apply the loaded font size to the app and markdown renderer
            app = QApplication.instance()
            app_font = app.font()
            app_font.setPointSize(self.settings.font_size)
            app.setFont(app_font)
            MarkdownRenderer.set_font_size(self.settings.font_size)
            self.app_settings.add_recent(path)
            self._rebuild_recent_menu()
            self.show_status(f"Opened: {os.path.basename(path)}",  type=StatusMessageType.OPEN )

    def reconstruct_scene(self, scene, data):
        node_map = {}
        for ndata in data["nodes"]:
            # Correct strings to Enums
            etype = next((e for e in NodeType if e.value == ndata["event_type"]), NodeType.NOTE)
            # Create object
            node = NodeData(ndata["name"], etype)
            node.id = ndata["id"]
            node.markdown_content = ndata["markdown"]
            node.stage_notes = ndata["stage_notes"]
            node.selected_characters = ndata.get("selected_characters", [])
            node.globals_vars = ndata.get("globals_vars", {})
            node.variable_name = ndata.get("variable_name", "")
            node.variable_op = ndata.get("variable_op", "Add")
            node.variable_delta = ndata.get("variable_delta", 0.0)
            node.image_path = ndata["image_path"]
            node.show_bg_image = ndata["show_bg"]
            node.is_subnetwork = ndata["is_subnetwork"]
            # Load named ports (keys stored as strings in JSON → convert back to int)
            raw_in = ndata.get("input_ports", {"0": "Default"})
            node.input_ports = {int(k): v for k, v in raw_in.items()}
            raw_out = ndata.get("output_ports", {"0": "Default"})
            node.output_ports = {int(k): v for k, v in raw_out.items()}
            
            # Subnetwork?
            if node.is_subnetwork and ndata["subnetwork"]:
                sub_scene = GraphScene(self.settings)
                sub_scene.parent_scene = scene
                sub_scene.name = node.name
                self.reconstruct_scene(sub_scene, ndata["subnetwork"])
                node.subnetwork_id = sub_scene
                
            # Add to scene
            item = scene.add_node(ndata["pos"][0], ndata["pos"][1], node)
            node_map[node.id] = item
            
            # Set up subnetwork callback for live updates
            if node.is_subnetwork and node.subnetwork_id:
                sub = node.subnetwork_id
                sub.itemAddedOrRemoved = lambda ni=item: ni.create_sockets()

        # Connections
        for cdata in data["connections"]:
            start_node = node_map.get(cdata["start_id"])
            end_node = node_map.get(cdata["end_id"])
            if start_node and end_node:
                si = cdata["start_idx"]
                ei = cdata["end_idx"]
                if si < len(start_node.outputs) and ei < len(end_node.inputs):
                    conn = scene.create_connection(start_node.outputs[si], end_node.inputs[ei])
                    if conn:
                        conn.line_style = Qt.PenStyle(cdata.get("line_style", 1))
                        conn.line_color = cdata.get("line_color", "#646464")

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)

    # Use Fusion style so the QPalette is respected uniformly across all controls.
    app.setStyle("Fusion")

    # Slightly-brighter dark palette for the GUI chrome.
    # Content areas (graph canvas, text editors, AI output) keep their own
    # explicit dark backgrounds and are not affected by these palette values.
    _p = QPalette()
    _p.setColor(QPalette.ColorRole.Window,          QColor("#404040"))  # panel / sidebar bg
    _p.setColor(QPalette.ColorRole.WindowText,      QColor("#dddddd"))
    _p.setColor(QPalette.ColorRole.Base,            QColor("#1e1e1e"))  # text-editor / list bg (kept dark)
    _p.setColor(QPalette.ColorRole.AlternateBase,   QColor("#353535"))
    _p.setColor(QPalette.ColorRole.ToolTipBase,     QColor("#363636"))
    _p.setColor(QPalette.ColorRole.ToolTipText,     QColor("#dddddd"))
    _p.setColor(QPalette.ColorRole.Text,            QColor("#dddddd"))
    _p.setColor(QPalette.ColorRole.Button,          QColor("#353535"))  # button / header bg
    _p.setColor(QPalette.ColorRole.ButtonText,      QColor("#dddddd"))
    _p.setColor(QPalette.ColorRole.BrightText,      QColor("#ffffff"))
    _p.setColor(QPalette.ColorRole.Link,            QColor("#5c9fd8"))
    _p.setColor(QPalette.ColorRole.Highlight,       QColor("#2979cc"))
    _p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    _p.setColor(QPalette.ColorRole.Light,           QColor("#5e5e5e"))
    _p.setColor(QPalette.ColorRole.Midlight,        QColor("#545454"))
    _p.setColor(QPalette.ColorRole.Mid,             QColor("#4a4a4a"))
    _p.setColor(QPalette.ColorRole.Dark,            QColor("#2e2e2e"))
    _p.setColor(QPalette.ColorRole.Shadow,          QColor("#1a1a1a"))
    _p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#666666"))
    app.setPalette(_p)
    app.setStyleSheet("""
        QScrollBar:vertical {
            background: transparent;
            width: 6px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: rgba(255, 255, 255, 70);
            min-height: 20px;
            border-radius: 3px;
        }
        QScrollBar::handle:vertical:hover {
            background: rgba(255, 255, 255, 130);
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {
            background: transparent;
        }
        QScrollBar:horizontal {
            background: transparent;
            height: 6px;
            margin: 0px;
        }
        QScrollBar::handle:horizontal {
            background: rgba(255, 255, 255, 70);
            min-width: 20px;
            border-radius: 3px;
        }
        QScrollBar::handle:horizontal:hover {
            background: rgba(255, 255, 255, 130);
        }
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {
            width: 0px;
        }
        QScrollBar::add-page:horizontal,
        QScrollBar::sub-page:horizontal {
            background: transparent;
        }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
