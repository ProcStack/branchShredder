from enum import Enum

class NodeType(Enum):
    NOTE = "Note"
    DIALOGUE = "Dialogue"
    CHARACTER = "Character"
    EVENT = "Event"
    INFO = "Info"
    SECRET = "Secret"
    START = "Start"
    END = "End"
    DOT = "Dot"
    GLOBALS = "Globals"

    @classmethod
    def list(cls):
        return [c.value for c in cls]

# Default (width, height) per NodeType - single source of truth used by graph_items
NODE_SIZES = {
    NodeType.START:    (100, 64),
    NodeType.END:      (100, 64),
    NodeType.DOT:      (30,  30),
    NodeType.DIALOGUE: (150, 50),
    NodeType.CHARACTER: (150, 50),
    NodeType.NOTE:     (150, 80),
    NodeType.EVENT:    (150, 80),
    NodeType.INFO:     (150, 80),
    NodeType.SECRET:   (150, 80),
    NodeType.GLOBALS:  (220, 100),
}

class NodeData:
    def __init__(self, name="New Node", event_type=NodeType.NOTE):
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
        self.selected_characters = [] # Characters active in this DIALOGUE/EVENT node
        self.globals_vars = {}         # {name: default_value} - only for GLOBALS nodes
        self.variable_name = ""        # which variable this node affects
        self.variable_op = "Add"       # Set / Add / Subtract / Multiply
        self.variable_delta = 0.0      # the value to apply
        # Named ports: dict of {index(int): name(str)}
        # If only one port and name is "Default", the name is omitted from path display.
        self.input_ports: dict = {0: "Default"}   # input connection ports
        self.output_ports: dict = {0: "Default"}  # output connection ports

class ProjectSettings:
    def __init__(self):
        self.node_colors = {
            NodeType.NOTE.value: "#808080",     # Mid Gray
            NodeType.DIALOGUE.value: "#4A90E2", # Blue
            NodeType.CHARACTER.value: "#e2b57f", # Beige
            NodeType.EVENT.value: "#28a637",    # Mid Green
            NodeType.INFO.value: "#f1cc5c",     # Bright Yellow
            NodeType.SECRET.value: "#BD10E0",   # Purple
            NodeType.START.value: "#8915dc",    # Violet
            NodeType.END.value: "#9e78b9",       # Lavender
            NodeType.DOT.value: "#aaaaaa",       # Light Gray
            NodeType.GLOBALS.value: "#1a1a2e",   # Dark Navy
            "SUBNETWORK": "#417505"              # Dark Green
        }
        self.bg_image_scale = 5.0 # 500%
        self.bg_image_offset_x = 0
        self.bg_image_offset_y = 0
        self.show_grid = True
        self.grid_minor = 60
        self.grid_major = 180
        self.create_node_on_empty_drop = True
        self.socket_size = 14
        self.font_size = 10
        self.show_ai_bar = False
        self.project_system_prompt = ""
