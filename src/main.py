from PyQt6.QtWidgets import (QMainWindow, QGraphicsView, QGraphicsScene, 
                             QWidget, QHBoxLayout, QVBoxLayout, 
                             QPushButton, QToolBar, QMessageBox, 
                             QInputDialog, QApplication, QFileDialog,
                             QSplitter)
from PyQt6.QtCore import Qt, pyqtSignal, QPointF
from PyQt6.QtGui import QAction, QPainter, QColor, QPen

import os
from models import NodeData, EventType, ProjectSettings
from graph_items import BaseNodeItem, ConnectionItem, SocketItem
from widgets import NodeInspector, SettingsSidebar, StoryWritingBar, ConnectionInspector
from manager import ProjectManager

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

        GRID_MINOR = 60
        GRID_MAJOR = 180

        # Snap the exposed rect outward to the nearest grid multiple so lines
        # always start off-screen and never leave a partial-cell gap at edges.
        left   = int(rect.left())   - (int(rect.left())   % GRID_MINOR)
        top    = int(rect.top())    - (int(rect.top())    % GRID_MINOR)
        right  = int(rect.right())  + GRID_MINOR
        bottom = int(rect.bottom()) + GRID_MINOR

        minor_pen = QPen(QColor(34, 34, 34), 0)   # 0 = cosmetic 1px regardless of zoom
        major_pen = QPen(QColor(50, 50, 50), 0)

        # Vertical lines
        x = left
        while x <= right:
            painter.setPen(major_pen if x % GRID_MAJOR == 0 else minor_pen)
            painter.drawLine(x, top, x, bottom)
            x += GRID_MINOR

        # Horizontal lines
        y = top
        while y <= bottom:
            painter.setPen(major_pen if y % GRID_MAJOR == 0 else minor_pen)
            painter.drawLine(left, y, right, y)
            y += GRID_MINOR

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
            items = self.items(event.pos())
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
                self._current_connection.socket_end = found_socket
                self._current_connection.updatePath()
                # Finalize connection lists
                self._current_connection.socket_start.connections.append(self._current_connection)
                found_socket.connections.append(self._current_connection)
                self._current_connection = None
            else:
                self.scene().removeItem(self._current_connection)
                self._current_connection = None

        # Check for drop-on-curve insertion
        if (event.button() == Qt.MouseButton.LeftButton and
            self._drag_node and self._drag_start_pos):
            node = self._drag_node
            delta = node.pos() - self._drag_start_pos
            if abs(delta.x()) > 1 or abs(delta.y()) > 1:
                # Node was moved — check if it landed on a connection
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
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        if self._current_connection:
            self._current_connection.last_pos = self.mapToScene(event.pos())
            self._current_connection.updatePath()

        if hasattr(self, '_right_click_zoom') and self._right_click_zoom:
            diff = event.pos().y() - self._last_mouse_pos.y()
            factor = 1.001 ** -diff
            self.scale(factor, factor)
            self._last_mouse_pos = event.pos()
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        item = self.itemAt(event.pos())
        # Traverse up to find BaseNodeItem if double clicked on label/image
        temp = item
        while temp and not isinstance(temp, BaseNodeItem):
            temp = temp.parentItem()
        if isinstance(temp, BaseNodeItem):
            self.handle_node_double_click(temp)
        else:
            super().mouseDoubleClickEvent(event)

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
            in_data = NodeData("Start", EventType.START)
            out_data = NodeData("End", EventType.END)
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

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("branchShredder")
        self.resize(1200, 800)
        
        self.settings = ProjectSettings()
        
        # Main vertical splitter (Graph on top, Story on bottom)
        self.v_splitter = QSplitter(Qt.Orientation.Vertical)
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
        
        self.v_splitter.addWidget(self.top_container)
        self.v_splitter.addWidget(self.story_bar)
        self.v_splitter.setStretchFactor(0, 3)
        self.v_splitter.setStretchFactor(1, 1)
        
        self.view._selection_handler = self.on_selection_changed
        self.view.setScene(self.scene)
        
        self.create_menu()
        self.create_toolbar()

    def get_all_character_names(self):
        # Recursively find all character names from INPUT/START nodes in current and parent scenes
        names = []
        scene = self.view.scene()
        while scene:
            for item in scene.items():
                if isinstance(item, BaseNodeItem):
                    if item.node_data.event_type in [EventType.START, EventType.START]:
                        names.extend(item.node_data.character_names)
            scene = scene.parent_scene
        return list(set(names))

    def create_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")

        new_act = QAction("&New Project", self)
        new_act.triggered.connect(self.new_project)
        file_menu.addAction(new_act)

        load_act = QAction("&Open Project", self)
        load_act.triggered.connect(self.load_project)
        file_menu.addAction(load_act)

        save_act = QAction("&Save Project", self)
        save_act.triggered.connect(self.save_project)
        file_menu.addAction(save_act)

        file_menu.addSeparator()

        quit_act = QAction("&Quit", self)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

    def create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        
        self.add_node_act = QAction("Add Node", self)
        self.add_node_act.triggered.connect(lambda: self.view.scene().add_node(0,0))
        toolbar.addAction(self.add_node_act)
        
        self.del_node_act = QAction("Delete Node", self)
        self.del_node_act.triggered.connect(self.delete_selected_node)
        toolbar.addAction(self.del_node_act)

        self.back_act = QAction("Go Back", self)
        self.back_act.triggered.connect(self.go_back_scene)
        toolbar.addAction(self.back_act)
        
        toolbar.addSeparator()
        
        self.settings_act = QAction("Project Settings", self)
        self.settings_act.triggered.connect(self.toggle_settings_sidebar)
        toolbar.addAction(self.settings_act)

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
        node_item = None
        conn_item = None
        for item in items:
            if isinstance(item, BaseNodeItem) and not node_item:
                node_item = item
            elif isinstance(item, ConnectionItem) and not conn_item:
                conn_item = item
        
        if node_item:
            node_data = node_item.node_data
            self.inspector.set_node(node_data)
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
                
                self._selected_item.update_appearance()
                
                # Only recreate sockets when event type actually changed
                current_type = self._selected_item.node_data.event_type
                if getattr(self, '_last_event_type', None) != current_type:
                    self._selected_item.create_sockets()
                    self._last_event_type = current_type
                
                # If we renamed an END node inside a subnetwork, the parent subnetwork node needs to update labels
                scene = self.view.scene()
                if hasattr(scene, 'itemAddedOrRemoved'):
                    scene.itemAddedOrRemoved()
            except RuntimeError:
                self._selected_item = None

    def on_settings_changed(self):
        # Update all nodes in current scene
        for item in self.view.scene().items():
            if isinstance(item, BaseNodeItem):
                item.update_appearance()

    def delete_selected_node(self):
        items = self.view.scene().selectedItems()
        if not items: return
        
        res = QMessageBox.question(self, "Delete", "Delete node?", 
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if res == QMessageBox.StandardButton.Yes:
            scene = self.view.scene()
            for item in items:
                if isinstance(item, BaseNodeItem):
                    # Local bypass logic: if node has 1 input connection and 1 output connection, bypass it
                    # Find all unique source sockets and destination sockets connected to this node
                    sources = []
                    dests = []
                    for sock in item.inputs:
                        for conn in sock.connections:
                            # source is start if end is us
                            src = conn.socket_start if conn.socket_end == sock else conn.socket_end
                            if src: sources.append(src)
                    for sock in item.outputs:
                        for conn in sock.connections:
                            dst = conn.socket_end if conn.socket_start == sock else conn.socket_start
                            if dst: dests.append(dst)
                    
                    if len(sources) == 1 and len(dests) == 1:
                        self.view.scene().create_connection(sources[0], dests[0])
                    
                    self.view.scene().removeItem(item)
                elif isinstance(item, ConnectionItem):
                    self.view.scene().removeItem(item)
            
            # Notify for subnetwork updates
            if hasattr(scene, 'itemAddedOrRemoved'):
                scene.itemAddedOrRemoved()

    def go_back_scene(self):
        curr = self.view.scene()
        if curr.parent_scene:
            self.view.setScene(curr.parent_scene)

    def _populate_default_scene(self, scene):
        """Add an unconnected Start node (left) and End node (right) to a blank scene."""
        scene.add_node(100, 300, NodeData("Start", EventType.START))
        scene.add_node(600, 300, NodeData("End", EventType.END))

    def new_project(self):
        self.settings = ProjectSettings()
        new_scene = GraphScene(self.settings)
        self._populate_default_scene(new_scene)
        self.view.setScene(new_scene)
        self.inspector.set_node(None)
        
    def save_project(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "JSON Files (*.json)")
        if path:
            mgr = ProjectManager()
            mgr.save_project(path, self.scene, self.settings)
            QMessageBox.information(self, "Save", f"Project saved to {path}")
            
    def load_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "JSON Files (*.json)")
        if path:
             mgr = ProjectManager()
             root_data = mgr.load_project(path, self.settings)
             # Basic reconstruction for root:
             new_scene = GraphScene(self.settings)
             self.reconstruct_scene(new_scene, root_data)
             self.view.setScene(new_scene)
             self.scene = new_scene # Update main ref
             QMessageBox.information(self, "Load", f"Project loaded from {path}")

    def reconstruct_scene(self, scene, data):
        node_map = {}
        for ndata in data["nodes"]:
            # Correct strings to Enums
            etype = next((e for e in EventType if e.value == ndata["event_type"]), EventType.NOTE)
            # Create object
            node = NodeData(ndata["name"], etype)
            node.id = ndata["id"]
            node.markdown_content = ndata["markdown"]
            node.stage_notes = ndata["stage_notes"]
            node.character_names = ndata["characters"]
            node.image_path = ndata["image_path"]
            node.show_bg_image = ndata["show_bg"]
            node.is_subnetwork = ndata["is_subnetwork"]
            
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
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
