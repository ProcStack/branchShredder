"""
ws_client.py  —  procMessenger WebSocket client for branchShredder.

Registers branchShredder on a procMessenger server and handles incoming
messages from network peers (mobile app, other scripts, etc.).

Supported message types received:
    query_nodes    — return INFO / CHARACTER nodes from the loaded project
    find_nodes     — return a lightweight index of nodes keyed by ID
    get_node       — return the full content of a single node by ID
    update_node    — update content / name of a node by ID
    system_prompt  — return the built-in + project system prompt
    llm_chat       — forward an LLM request to AIManager and reply
    edit_story     — alias for llm_chat (protocol compatibility)
    system         — application-level commands dispatched by action:
                       recent_scenes, open_recent, new_scene, save_scene
    ping           — responds with pong

Configuration is read from .env in the project root:
    PROC_MESSENGER_ENABLED=true
    PROC_MESSENGER_HOST=192.168.1.154
    PROC_MESSENGER_PORT=9734
    PROC_MESSENGER_CLIENT_NAME=branchShredder
"""

import json
import threading
import time
import uuid
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Qt-thread bridge
# ---------------------------------------------------------------------------

class _MainThreadBridge:
    """Thread-safe bridge for read-only access to Qt scene objects.

    The WebSocket thread cannot safely call Qt methods directly.  Instead it
    places work items on a queue; the Qt main thread drains the queue via a
    QTimer and delivers results back through threading.Event / result slots.
    """

    def __init__(self):
        import queue
        self._queue = queue.Queue()
        self._timer = None

    def start(self):
        """Start the drain timer — must be called from the Qt main thread."""
        from PyQt6.QtCore import QTimer
        self._timer = QTimer()
        self._timer.setInterval(50)          # poll every 50 ms
        self._timer.timeout.connect(self._drain)
        self._timer.start()

    def stop(self):
        if self._timer:
            self._timer.stop()
            self._timer = None

    def _drain(self):
        """Called on the Qt main thread; runs all pending work items."""
        import queue as _queue
        while True:
            try:
                fn = self._queue.get_nowait()
            except _queue.Empty:
                break
            try:
                fn()
            except Exception:
                pass

    def run_on_main(self, fn, timeout: float = 5.0):
        """Schedule *fn* on the Qt main thread and block until it returns.

        Returns the value returned by *fn*, or raises any exception it raised.
        """
        result = [None]
        exc = [None]
        done = threading.Event()

        def _wrapper():
            try:
                result[0] = fn()
            except Exception as e:
                exc[0] = e
            finally:
                done.set()

        self._queue.put(_wrapper)
        done.wait(timeout=timeout)
        if exc[0]:
            raise exc[0]
        return result[0]


# ---------------------------------------------------------------------------
# WebSocket client
# ---------------------------------------------------------------------------

class BranchShredderWSClient:
    """Persistent WebSocket connection to a procMessenger server.

    Parameters
    ----------
    host, port:
        Server address read from .env.
    client_name:
        The name used when registering (``source`` field in all messages).
    scene_getter:
        Callable that returns the current ``GraphScene`` (may return *None*
        if no project is loaded).
    settings_getter:
        Callable that returns the current ``ProjectSettings``.
    ai_manager:
        ``AIManager`` instance used to service ``llm_chat`` requests.
    bridge:
        ``_MainThreadBridge`` instance for thread-safe Qt scene access.
    app_settings_getter:
        Callable that returns the ``AppSettingsManager`` (for recent projects).
    open_project_fn:
        Callable that accepts a file path and opens it as the active project.
        Must be safe to call from the Qt main thread (dispatched via bridge).
    new_project_fn:
        Callable that creates a fresh empty project (no arguments).
        Must be safe to call from the Qt main thread (dispatched via bridge).
    save_project_fn:
        Callable ``(path: str) -> None`` that saves the current project to
        *path*.  If *path* is ``None`` the current project path is used.
        Must be safe to call from the Qt main thread (dispatched via bridge).
    project_root:
        Absolute path to the directory used when auto-locating the default
        ``projects/`` save folder (typically the branchShredder repo root).
    """

    def __init__(
        self,
        host: str,
        port: int,
        client_name: str,
        scene_getter,
        settings_getter,
        ai_manager,
        bridge: _MainThreadBridge,
        app_settings_getter=None,
        open_project_fn=None,
        new_project_fn=None,
        save_project_fn=None,
        project_root: str = "",
    ):
        self.host = host
        self.port = port
        self.client_name = client_name
        self._scene_getter = scene_getter
        self._settings_getter = settings_getter
        self._ai_manager = ai_manager
        self._bridge = bridge
        self._app_settings_getter = app_settings_getter
        self._open_project_fn = open_project_fn
        self._new_project_fn = new_project_fn
        self._save_project_fn = save_project_fn
        self._project_root = project_root
        self._thread: threading.Thread | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="bs-ws-client", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        # The thread is daemon so it will be reaped automatically; we just
        # signal it to exit the reconnect loop gracefully.

    # ------------------------------------------------------------------
    # Connection loop (runs on daemon thread)
    # ------------------------------------------------------------------

    def _run_loop(self):
        """Reconnect loop — retries every 10 s on any connection failure."""
        try:
            import websockets.sync.client as _wsc
        except ImportError:
            # websockets not installed — silently no-op
            return

        uri = f"ws://{self.host}:{self.port}"
        while self._running:
            try:
                with _wsc.connect(uri, open_timeout=8, close_timeout=4) as ws:
                    self._register(ws)
                    for raw in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        self._dispatch(ws, msg)
            except Exception:
                if not self._running:
                    break
                time.sleep(10)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def _register(self, ws):
        ws.send(json.dumps({
            "id": str(uuid.uuid4()),
            "type": "register",
            "source": self.client_name,
            "target": "server",
            "timestamp": _now_iso(),
            "flags": {},
            "payload": {
                "clientType": "python",
                "capabilities": [
                    "edit_story",
                    "llm_chat",
                    "query_nodes",
                    "find_nodes",
                    "get_node",
                    "update_node",
                    "system_prompt",
                    "system",
                ],
                "hostname": "",
                "nickname": "branchShredder",
            },
        }))

    # ------------------------------------------------------------------
    # Message dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, ws, msg: dict):
        t = msg.get("type", "")
        if t == "ping":
            self._send_pong(ws, msg)
        elif t in ("edit_story", "llm_chat"):
            self._handle_llm_chat(ws, msg)
        elif t == "query_nodes":
            self._handle_query_nodes(ws, msg)
        elif t == "find_nodes":
            self._handle_find_nodes(ws, msg)
        elif t == "get_node":
            self._handle_get_node(ws, msg)
        elif t == "update_node":
            self._handle_update_node(ws, msg)
        elif t == "system_prompt":
            self._handle_system_prompt(ws, msg)
        elif t == "system":
            self._handle_system(ws, msg)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _envelope(self, original_msg: dict, payload: dict) -> str:
        return json.dumps({
            "id": str(uuid.uuid4()),
            "type": original_msg.get("type", ""),
            "source": self.client_name,
            "target": original_msg.get("source", ""),
            "timestamp": _now_iso(),
            "flags": {"correlationId": original_msg.get("id", "")},
            "payload": payload,
        })

    def _send_pong(self, ws, ping_msg: dict):
        ws.send(json.dumps({
            "id": str(uuid.uuid4()),
            "type": "pong",
            "source": self.client_name,
            "target": "server",
            "timestamp": _now_iso(),
            "flags": {},
            "payload": {},
        }))

    # ------------------------------------------------------------------
    # llm_chat / edit_story
    # ------------------------------------------------------------------

    def _handle_llm_chat(self, ws, msg: dict):
        payload = msg.get("payload", {})
        user_message = payload.get("message", "")
        model_id = payload.get("model", "")

        # Send "thinking" immediately
        ws.send(self._envelope(msg, {"status": "thinking", "message": ""}))

        # Optionally prepend node context supplied by the caller
        prompt = user_message
        node_context = payload.get("nodeContext", "")
        if node_context:
            prompt = node_context + "\n\n--- User Prompt ---\n" + prompt

        # Project system prompt (thread-safe read via bridge)
        try:
            settings = self._bridge.run_on_main(self._settings_getter)
        except Exception:
            settings = None
        project_sys = getattr(settings, "project_system_prompt", "") if settings else ""

        # Fall back to first available model if none specified
        if not model_id:
            available = self._ai_manager.get_available_models()
            model_id = available[0][1] if available else ""

        if not model_id:
            ws.send(self._envelope(msg, {
                "status": "error",
                "message": "No AI model available. Configure an API key in .env.",
            }))
            return

        result = self._query_sync(model_id, prompt, project_sys)
        status = "error" if result.startswith("Error:") else "complete"
        ws.send(self._envelope(msg, {"status": status, "message": result}))

    def _query_sync(self, model_id: str, prompt: str, project_sys: str) -> str:
        """Block the calling thread until AIManager returns a response."""
        result_holder: list = [None]
        error_holder: list = [None]
        event = threading.Event()

        def _cb(text):
            result_holder[0] = text
            event.set()

        def _err(msg):
            error_holder[0] = msg
            event.set()

        self._ai_manager.query(model_id, prompt, project_sys, callback=_cb, error_callback=_err)
        event.wait(timeout=120)
        if error_holder[0]:
            return f"Error: {error_holder[0]}"
        return result_holder[0] or ""

    # ------------------------------------------------------------------
    # query_nodes
    # ------------------------------------------------------------------

    def _handle_query_nodes(self, ws, msg: dict):
        payload = msg.get("payload", {})
        filt = payload.get("filter", {})
        requested_types = filt.get("types", ["Info", "Character"])
        include_subnets = filt.get("includeSubnetworks", True)

        try:
            nodes = self._bridge.run_on_main(
                lambda: self._collect_nodes(requested_types, include_subnets)
            )
        except Exception as exc:
            ws.send(self._envelope(msg, {"nodes": [], "error": str(exc)}))
            return

        ws.send(self._envelope(msg, {"nodes": nodes or []}))

    def _collect_nodes(self, node_types: list, include_subnets: bool) -> list:
        """Collect matching nodes from the full scene tree.

        Must be called on the Qt main thread (via _bridge.run_on_main).
        """
        scene = self._scene_getter()
        if not scene:
            return []

        from .graph_items import BaseNodeItem

        results = []
        seen_ids: set = set()

        def _walk(sc, scene_label: str):
            for item in sc.items():
                if not isinstance(item, BaseNodeItem):
                    continue
                nd = item.node_data
                if nd.id in seen_ids:
                    continue
                seen_ids.add(nd.id)

                if nd.event_type.value in node_types:
                    paths = item.compute_paths()
                    results.append({
                        "name": nd.name,
                        "type": nd.event_type.value,
                        "content": nd.markdown_content,
                        "stageNotes": nd.stage_notes,
                        "scenePath": scene_label,
                        "nodePaths": paths,
                        "selectedCharacters": nd.selected_characters,
                    })

                if include_subnets and nd.is_subnetwork and nd.subnetwork_id:
                    _walk(nd.subnetwork_id, f"{scene_label} > {nd.name}")

        _walk(scene, getattr(scene, "name", "Root"))
        return results

    # ------------------------------------------------------------------
    # system_prompt
    # ------------------------------------------------------------------

    def _handle_system_prompt(self, ws, msg: dict):
        try:
            settings = self._bridge.run_on_main(self._settings_getter)
        except Exception:
            settings = None

        project_ctx = getattr(settings, "project_system_prompt", "") if settings else ""
        app_prompt = self._ai_manager.SYSTEM_PROMPT_APP
        scripting_prompt = self._ai_manager._get_scripting_prompt()
        full_prompt = self._ai_manager.get_full_app_prompt()
        if project_ctx.strip():
            full_prompt += "\n\n--- Project Context ---\n" + project_ctx.strip()

        ws.send(self._envelope(msg, {
            "fullSystemPrompt": full_prompt,
            "parts": {
                "appPrompt": app_prompt,
                "scriptingPrompt": scripting_prompt,
                "projectContext": project_ctx,
            },
        }))

    # ------------------------------------------------------------------
    # find_nodes  — lightweight index keyed by node ID
    # ------------------------------------------------------------------

    def _handle_find_nodes(self, ws, msg: dict):
        payload = msg.get("payload", {})
        filt = payload.get("filter", {})
        node_types = filt.get("types", ["Info", "Character"])
        include_subnets = filt.get("includeSubnetworks", True)

        try:
            index = self._bridge.run_on_main(
                lambda: self._collect_node_index(node_types, include_subnets)
            )
        except Exception as exc:
            ws.send(self._envelope(msg, {"nodes": {}, "error": str(exc)}))
            return

        ws.send(self._envelope(msg, {"nodes": index or {}}))

    def _collect_node_index(self, node_types: list, include_subnets: bool) -> dict:
        """Return a dict {node_id: {name, type, scenePath, nodePaths}}.

        Must be called on the Qt main thread (via _bridge.run_on_main).
        """
        scene = self._scene_getter()
        if not scene:
            return {}

        from .graph_items import BaseNodeItem

        result = {}
        seen_ids: set = set()

        def _walk(sc, scene_label: str):
            for item in sc.items():
                if not isinstance(item, BaseNodeItem):
                    continue
                nd = item.node_data
                if nd.id in seen_ids:
                    continue
                seen_ids.add(nd.id)

                if nd.event_type.value in node_types:
                    result[nd.id] = {
                        "name": nd.name,
                        "type": nd.event_type.value,
                        "scenePath": scene_label,
                        "nodePaths": item.compute_paths(),
                    }

                if include_subnets and nd.is_subnetwork and nd.subnetwork_id:
                    _walk(nd.subnetwork_id, f"{scene_label} > {nd.name}")

        _walk(scene, getattr(scene, "name", "Root"))
        return result

    # ------------------------------------------------------------------
    # get_node  — full content of one node by ID
    # ------------------------------------------------------------------

    def _handle_get_node(self, ws, msg: dict):
        node_id = msg.get("payload", {}).get("nodeId", "")
        if not node_id:
            ws.send(self._envelope(msg, {"error": "nodeId is required"}))
            return

        try:
            result = self._bridge.run_on_main(lambda: self._fetch_node(node_id))
        except Exception as exc:
            ws.send(self._envelope(msg, {"error": str(exc)}))
            return

        if result is None:
            ws.send(self._envelope(msg, {"error": f"Node '{node_id}' not found"}))
        else:
            ws.send(self._envelope(msg, result))

    def _fetch_node(self, node_id: str):
        """Return a dict of all node fields, or None if not found.

        Must be called on the Qt main thread (via _bridge.run_on_main).
        """
        found = self._locate_node_by_id(node_id)
        if found is None:
            return None
        item, scene_label = found
        nd = item.node_data
        return {
            "nodeId": nd.id,
            "name": nd.name,
            "type": nd.event_type.value,
            "content": nd.markdown_content,
            "stageNotes": nd.stage_notes,
            "selectedCharacters": nd.selected_characters,
            "scenePath": scene_label,
            "nodePaths": item.compute_paths(),
        }

    # ------------------------------------------------------------------
    # update_node  — write new content / name back into the live scene
    # ------------------------------------------------------------------

    def _handle_update_node(self, ws, msg: dict):
        payload = msg.get("payload", {})
        node_id = payload.get("nodeId", "")
        if not node_id:
            ws.send(self._envelope(msg, {"error": "nodeId is required"}))
            return

        new_content = payload.get("content")   # None means "don't change"
        new_name = payload.get("name")          # None means "don't change"

        try:
            updated_name = self._bridge.run_on_main(
                lambda: self._apply_node_update(node_id, new_content, new_name)
            )
        except Exception as exc:
            ws.send(self._envelope(msg, {"nodeId": node_id, "status": "error", "error": str(exc)}))
            return

        if updated_name is None:
            ws.send(self._envelope(msg, {"nodeId": node_id, "status": "error",
                                         "error": f"Node '{node_id}' not found"}))
        else:
            ws.send(self._envelope(msg, {"nodeId": node_id, "status": "complete",
                                         "name": updated_name}))

    def _apply_node_update(self, node_id: str, content, name):
        """Apply content/name changes to the live node item.

        Returns the (possibly updated) node name on success, or None if not found.
        Must be called on the Qt main thread (via _bridge.run_on_main).
        """
        found = self._locate_node_by_id(node_id)
        if found is None:
            return None
        item, _ = found
        nd = item.node_data
        if content is not None:
            nd.markdown_content = content
        if name is not None and name != nd.name:
            nd.name = name
            item.update_appearance()  # refreshes the visible title label
        return nd.name

    # ------------------------------------------------------------------
    # Shared scene-traversal helpers
    # ------------------------------------------------------------------

    def _locate_node_by_id(self, node_id: str):
        """Walk the full scene tree and return (BaseNodeItem, scene_label) or None.

        Must be called on the Qt main thread (via _bridge.run_on_main).
        """
        scene = self._scene_getter()
        if not scene:
            return None

        from .graph_items import BaseNodeItem

        seen_ids: set = set()

        def _walk(sc, scene_label: str):
            for item in sc.items():
                if not isinstance(item, BaseNodeItem):
                    continue
                nd = item.node_data
                if nd.id in seen_ids:
                    continue
                seen_ids.add(nd.id)
                if nd.id == node_id:
                    return (item, scene_label)
                if nd.is_subnetwork and nd.subnetwork_id:
                    found = _walk(nd.subnetwork_id, f"{scene_label} > {nd.name}")
                    if found:
                        return found
            return None

        return _walk(scene, getattr(scene, "name", "Root"))

    # ------------------------------------------------------------------
    # system  — application-level command dispatcher
    # ------------------------------------------------------------------

    # Actions accepted in payload.actions[] (or the legacy single payload.action):
    #   recent_scenes  — list recently opened projects
    #   open_recent    — open a project by path (requires payload.path)
    #   new_scene      — create a fresh empty project
    #   save_scene     — save the current project (requires payload.filename for new files)

    def _handle_system(self, ws, msg: dict):
        payload = msg.get("payload", {})
        # Support both a single action string and an actions array.
        actions = payload.get("actions")
        if actions is None:
            single = payload.get("action", "")
            actions = [single] if single else []

        if not actions:
            ws.send(self._envelope(msg, {"status": "error", "error": "No action specified"}))
            return

        results = {}
        for action in actions:
            try:
                results[action] = self._run_system_action(action, payload)
            except Exception as exc:
                results[action] = {"status": "error", "error": str(exc)}

        ws.send(self._envelope(msg, {"results": results}))

    def _run_system_action(self, action: str, payload: dict) -> dict:
        import os
        if action == "recent_scenes":
            return self._action_recent_scenes()
        elif action == "open_recent":
            return self._action_open_recent(payload.get("path", ""))
        elif action == "new_scene":
            return self._action_new_scene()
        elif action == "save_scene":
            return self._action_save_scene(payload.get("filename", ""))
        else:
            return {"status": "error", "error": f"Unknown action: {action}"}

    # -- action helpers --

    def _action_recent_scenes(self) -> dict:
        import os
        app_settings = self._app_settings_getter() if self._app_settings_getter else None
        recent_paths = app_settings.recent_projects if app_settings else []
        scenes = [
            {"path": p, "name": os.path.splitext(os.path.basename(p))[0]}
            for p in recent_paths
        ]
        return {"status": "complete", "scenes": scenes}

    def _action_open_recent(self, path: str) -> dict:
        import os
        if not path:
            return {"status": "error", "error": "path is required"}
        if not os.path.exists(path):
            return {"status": "error", "error": f"File not found: {path}"}
        if not self._open_project_fn:
            return {"status": "error", "error": "open_project not configured"}
        name = os.path.splitext(os.path.basename(path))[0]
        self._bridge.run_on_main(lambda: self._open_project_fn(path))
        return {"status": "complete", "name": name, "path": path}

    def _action_new_scene(self) -> dict:
        if not self._new_project_fn:
            return {"status": "error", "error": "new_project not configured"}
        self._bridge.run_on_main(self._new_project_fn)
        return {"status": "complete"}

    def _action_save_scene(self, filename: str) -> dict:
        import os
        if not self._save_project_fn:
            return {"status": "error", "error": "save_project not configured"}

        # Determine the save path
        if filename:
            # Ensure .json extension
            if not filename.lower().endswith(".json"):
                filename += ".json"
            # If the caller gave just a bare name (no directory separators),
            # resolve it relative to the projects/ folder inside the repo root.
            if not os.path.dirname(filename):
                projects_dir = os.path.join(self._project_root, "projects")
                os.makedirs(projects_dir, exist_ok=True)
                path = os.path.join(projects_dir, filename)
            else:
                path = filename
        else:
            # No filename supplied — save in place (existing project only)
            path = None

        name = os.path.splitext(os.path.basename(path))[0] if path else "(current)"
        self._bridge.run_on_main(lambda: self._save_project_fn(path))
        return {"status": "complete", "name": name, "path": path or ""}
