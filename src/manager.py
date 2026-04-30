import json
import os

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_SETTINGS_PATH = os.path.join(_APP_ROOT, "app_settings.json")
_MAX_RECENT = 10


class AppSettingsManager:
    """Manages the application-level settings file at the project root.

    The file is a general-purpose JSON store. Keys used so far:
        recent_projects  – list of absolute paths (most recent first)
    """

    def __init__(self, path=None):
        self.path = path or _APP_SETTINGS_PATH
        self._data = {}
        self.load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = {}

    def save(self):
        try:
            with open(self.path, 'w') as f:
                json.dump(self._data, f, indent=4)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Recent projects
    # ------------------------------------------------------------------

    @property
    def recent_projects(self):
        return list(self._data.get("recent_projects", []))

    def add_recent(self, path):
        path = os.path.normpath(path)
        recent = self.recent_projects
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        self._data["recent_projects"] = recent[:_MAX_RECENT]
        self.save()

    def remove_recent(self, path):
        path = os.path.normpath(path)
        recent = self.recent_projects
        if path in recent:
            recent.remove(path)
            self._data["recent_projects"] = recent
            self.save()

    def clear_recent(self):
        self._data["recent_projects"] = []
        self.save()


class ProjectManager:
    def __init__(self, root_path=None):
        self.root_path = root_path
        if root_path:
            self.media_path = os.path.join(root_path, "MediaAssets")
            os.makedirs(self.media_path, exist_ok=True)
        else:
            self.media_path = None

        self.current_project_path = None
        
    def serialize_node(self, node_item):
        data = node_item.node_data
        node_dict = {
            "id": data.id,
            "name": data.name,
            "event_type": data.event_type.value,
            "pos": [node_item.pos().x(), node_item.pos().y()],
            "markdown": data.markdown_content,
            "stage_notes": data.stage_notes,
            "selected_characters": data.selected_characters,
            "globals_vars": data.globals_vars,
            "variable_name": data.variable_name,
            "variable_op": data.variable_op,
            "variable_delta": data.variable_delta,
            "image_path": data.image_path,
            "show_bg": data.show_bg_image,
            "is_subnetwork": data.is_subnetwork,
            "input_ports": {str(k): v for k, v in data.input_ports.items()},
            "output_ports": {str(k): v for k, v in data.output_ports.items()},
            "subnetwork": None
        }
        if data.is_subnetwork and data.subnetwork_id:
            node_dict["subnetwork"] = self.serialize_scene(data.subnetwork_id)
        return node_dict

    def serialize_scene(self, scene):
        from .graph_items import BaseNodeItem, ConnectionItem
        nodes = []
        connections = []
        
        # We need a way to identify sockets uniquely for connections.
        # Since we use indices in create_sockets, we'll store (startNodeId, startIndex, endNodeId, endIndex)
        
        for item in scene.items():
            if isinstance(item, BaseNodeItem):
                nodes.append(self.serialize_node(item))
            elif isinstance(item, ConnectionItem) and item.socket_end:
                # Normalize: start_sock must be output, end_sock must be input
                start_sock = item.socket_start
                end_sock = item.socket_end
                if start_sock.is_input:
                    start_sock, end_sock = end_sock, start_sock
                start_node = start_sock.parentItem()
                end_node = end_sock.parentItem()
                try:
                    start_idx = start_sock.node_item.outputs.index(start_sock)
                    end_idx = end_sock.node_item.inputs.index(end_sock)
                except ValueError:
                    continue  # Skip malformed connections
                connections.append({
                    "start_id": start_node.node_data.id,
                    "start_idx": start_idx,
                    "end_id": end_node.node_data.id,
                    "end_idx": end_idx,
                    "line_style": item.line_style.value,
                    "line_color": item.line_color
                })
        
        return {
            "name": getattr(scene, 'name', 'Root'),
            "nodes": nodes,
            "connections": connections
        }

    def parse_project_json_data(self, root_scene, settings):
        data = {
            "settings": {
                "colors": settings.node_colors,
                "scale": settings.bg_image_scale,
                "bg_offset_x": settings.bg_image_offset_x,
                "bg_offset_y": settings.bg_image_offset_y,
                "show_grid": settings.show_grid,
                "grid_minor": settings.grid_minor,
                "grid_major": settings.grid_major,
                "create_node_on_empty_drop": settings.create_node_on_empty_drop,
                "socket_size": settings.socket_size,
                "font_size": settings.font_size,
                "show_ai_bar": settings.show_ai_bar,
                "project_system_prompt": settings.project_system_prompt
            },
            "root": self.serialize_scene(root_scene)
        }
        return data

    def save_project_as(self, path, root_scene, settings):
        data = self.parse_project_json_data(root_scene, settings)
        with open(path, 'w') as f:
            json.dump(data, f, indent=4)
        self.current_project_path = path

    def save_project(self, root_scene, settings):
        if self.current_project_path:
            self.save_project_as(self.current_project_path, root_scene, settings)
        else:
            raise ValueError("No current project path. Use save_project_as to specify a path.")

    def load_project(self, path, settings):
        with open(path, 'r') as f:
            data = json.load(f)
        
        settings.node_colors.update(data["settings"].get("colors", {}))
        settings.bg_image_scale = data["settings"].get("scale", settings.bg_image_scale)
        settings.bg_image_offset_x = data["settings"].get("bg_offset_x", 0)
        settings.bg_image_offset_y = data["settings"].get("bg_offset_y", 0)
        settings.show_grid = data["settings"].get("show_grid", True)
        settings.grid_minor = data["settings"].get("grid_minor", 60)
        settings.grid_major = data["settings"].get("grid_major", 180)
        settings.create_node_on_empty_drop = data["settings"].get("create_node_on_empty_drop", True)
        settings.socket_size = data["settings"].get("socket_size", 14)
        settings.font_size = data["settings"].get("font_size", 10)
        settings.show_ai_bar = data["settings"].get("show_ai_bar", False)
        settings.project_system_prompt = data["settings"].get("project_system_prompt", "")
        
        self.current_project_path = path  
        return data["root"]

