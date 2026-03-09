from enum import Enum, auto

class EventType(Enum):
    NOTE = "Note"
    DIALOGUE = "Dialogue"
    EVENT = "Event"
    INFO = "Info"
    SECRET = "Secret"
    START = "Start"
    END = "End"

    @classmethod
    def list(cls):
        return [c.value for c in cls]

class NodeData:
    def __init__(self, name="New Node", event_type=EventType.NOTE):
        self.id = name + "_" + str(id(self))
        self.name = name
        self.event_type = event_type
        self.scene_actions = ""
        self.dialogue_choices = [] # List of strings/objects
        self.image_path = None
        self.show_bg_image = False
        self.location_zone = ""
        self.location_place = ""
        self.media_paths = [] # List of local paths
        self.is_subnetwork = False
        self.subnetwork_id = None # ID of the scene representing the subnetwork
        self.pos_x = 0
        self.pos_y = 0
        self.markdown_content = ""
        self.stage_notes = ""
        self.character_names = [] # Only used by INPUT nodes

class ProjectSettings:
    def __init__(self):
        self.node_colors = {
            EventType.NOTE.value: "#808080",     # Mid Gray
            EventType.DIALOGUE.value: "#4A90E2", # Blue
            EventType.EVENT.value: "#28a637",    # Mid Green
            EventType.INFO.value: "#F5A623",     # Orange
            EventType.SECRET.value: "#BD10E0",   # Purple
            EventType.START.value: "#8915dc",    # Violet
            EventType.END.value: "#9e78b9",       # Lavender
            "SUBNETWORK": "#417505"              # Dark Green
        }
        self.bg_image_scale = 5.0 # 500%
