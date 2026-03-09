import json
import os
import shutil
from models import NodeData, EventType, ProjectSettings

class ProjectManager:
    def __init__(self, root_path=None):
        self.root_path = root_path
        if root_path:
            self.media_path = os.path.join(root_path, "MediaAssets")
            os.makedirs(self.media_path, exist_ok=True)
        else:
            self.media_path = None
        
    def serialize_node(self, node_item):
        data = node_item.node_data
        node_dict = {
            "id": data.id,
            "name": data.name,
            "event_type": data.event_type.value,
            "pos": [node_item.pos().x(), node_item.pos().y()],
            "markdown": data.markdown_content,
            "stage_notes": data.stage_notes,
            "characters": data.character_names,
            "image_path": data.image_path,
            "show_bg": data.show_bg_image,
            "is_subnetwork": data.is_subnetwork,
            "subnetwork": None
        }
        if data.is_subnetwork and data.subnetwork_id:
            node_dict["subnetwork"] = self.serialize_scene(data.subnetwork_id)
        return node_dict

    def serialize_scene(self, scene):
        from graph_items import BaseNodeItem, ConnectionItem
        nodes = []
        connections = []
        
        # We need a way to identify sockets uniquely for connections.
        # Since we use indices in create_sockets, we'll store (startNodeId, startIndex, endNodeId, endIndex)
        
        for item in scene.items():
            if isinstance(item, BaseNodeItem):
                nodes.append(self.serialize_node(item))
            elif isinstance(item, ConnectionItem) and item.socket_end:
                start_node = item.socket_start.parentItem()
                end_node = item.socket_end.parentItem()
                start_idx = item.socket_start.node_item.outputs.index(item.socket_start)
                end_idx = item.socket_end.node_item.inputs.index(item.socket_end)
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

    def save_project(self, path, root_scene, settings):
        data = {
            "settings": {
                "colors": settings.node_colors,
                "scale": settings.bg_image_scale
            },
            "root": self.serialize_scene(root_scene)
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=4)

    def load_project(self, path, settings):
        with open(path, 'r') as f:
            data = json.load(f)
        
        settings.node_colors = data["settings"].get("colors", settings.node_colors)
        settings.bg_image_scale = data["settings"].get("scale", settings.bg_image_scale)
        
        return data["root"]

    # ... keeping other helper methods like organize_media if needed ...
