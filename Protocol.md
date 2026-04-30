# branchShredder — procMessenger WebSocket Protocol Extension

> These message types extend the **procMessenger** WebSocket protocol and are
> implemented exclusively by the **branchShredder** application.
> All messages follow the standard procMessenger envelope (see the procMessenger
> `Protocol.md` for the full envelope schema and shared message types).

---

## Overview

When branchShredder connects to a procMessenger server it registers with the
following capabilities:

```
edit_story  llm_chat  query_nodes  find_nodes  get_node  update_node
system_prompt  system  viewport  viewport_snapshot  viewport_info
```

This document covers the **viewport remote-control** additions.  All other
capabilities (`edit_story`, `llm_chat`, `query_nodes`, `find_nodes`,
`get_node`, `update_node`, `system_prompt`, `system`) are described in the
procMessenger shared protocol document.

---

## Viewport Remote-Control

branchShredder exposes three message types that let any connected client
(e.g. a mobile app) remotely control the graph viewport and receive PNG
screenshots in response.

---

### `viewport`

Execute a sequential pipeline of viewport commands.  The pipeline may move
the camera, zoom, centre on a node, and capture a PNG snapshot — all in a
single round-trip.

**Request** (any client → branchShredder):

```json
{
  "id": "uuid-v4",
  "type": "viewport",
  "source": "mobileApp",
  "target": "branchShredder",
  "timestamp": "2026-04-30T12:00:00Z",
  "flags": {},
  "payload": {
    "commands": [
      {"Move": [10, -15]},
      {"zoom": 0.98},
      {"viewport": "Render", "output": "WebSocket"}
    ]
  }
}
```

**Response — with image** (branchShredder → requester):

```json
{
  "type": "viewport",
  "payload": {
    "status": "complete",
    "image": "<base64-encoded PNG>",
    "format": "png"
  }
}
```

**Response — without image** (no `Render` command in pipeline):

```json
{
  "type": "viewport",
  "payload": {
    "status": "complete"
  }
}
```

**Response — error**:

```json
{
  "type": "viewport",
  "payload": {
    "status": "error",
    "error": "No viewport is available"
  }
}
```

#### Command Reference

Each element in `commands` is an object.  Multiple keys may appear in one
element; they are processed in insertion order.

| Key | Value type | Description |
|-----|-----------|-------------|
| `Move` | `[dx, dy]` | Pan the viewport by `dx`, `dy` **scene-coordinate units**. Positive X moves right; positive Y moves down. |
| `zoom` | `number` | Multiply the current zoom level by this factor. Values `< 1` zoom out, `> 1` zoom in. (e.g. `0.98` = zoom out 2%) |
| `center` | `[x, y]` | Centre the viewport on the absolute scene position `[x, y]`. |
| `center_node` | `string` | Centre the viewport on the node whose `id` matches this string. Searches subnets recursively. |
| `viewport` | `"Render"` | Capture the current viewport as a PNG.  This triggers the image response.  Must be last in the pipeline if an image is desired. |
| `output` | `"WebSocket"` | Declares where to deliver the rendered image.  Currently only `"WebSocket"` is supported. |
| `width` | `number` | Maximum output image width in pixels.  Aspect ratio is preserved. |
| `height` | `number` | Maximum output image height in pixels.  Aspect ratio is preserved. |

#### Pipeline Examples

Pan right, zoom out 2%, render:

```json
[
  {"Move": [10, -15]},
  {"zoom": 0.98},
  {"viewport": "Render", "output": "WebSocket"}
]
```

Centre on a known node and capture at 1280 × 720:

```json
[
  {"center_node": "abc123"},
  {"width": 1280, "height": 720},
  {"viewport": "Render", "output": "WebSocket"}
]
```

Move, zoom in, then render at full viewport resolution:

```json
[
  {"Move": [50, 0]},
  {"zoom": 1.1},
  {"viewport": "Render"}
]
```

---

### `viewport_snapshot`

Convenience shorthand for **"centre on a node → capture → return PNG"**.
Equivalent to composing a `viewport` pipeline manually.

**Request** (any client → branchShredder):

```json
{
  "id": "uuid-v4",
  "type": "viewport_snapshot",
  "source": "mobileApp",
  "target": "branchShredder",
  "timestamp": "2026-04-30T12:00:00Z",
  "flags": {},
  "payload": {
    "nodeId": "abc123",
    "zoom":   1.5,
    "width":  1280,
    "height": 720
  }
}
```

All payload fields are **optional**:

| Field | Type | Description |
|-------|------|-------------|
| `nodeId` | string | ID of the node to centre on before capturing.  Omit to capture the current viewport as-is. |
| `zoom` | number | **Absolute** zoom scale factor to apply before capturing (replaces current zoom). |
| `width` | number | Maximum output image width in pixels. |
| `height` | number | Maximum output image height in pixels. |

**Response — success**:

```json
{
  "type": "viewport_snapshot",
  "payload": {
    "status": "complete",
    "image": "<base64-encoded PNG>",
    "format": "png",
    "nodeId": "abc123"
  }
}
```

`nodeId` is `null` when no node was requested.

**Response — error**:

```json
{
  "type": "viewport_snapshot",
  "payload": {
    "status": "error",
    "error": "No viewport is available"
  }
}
```

---

### `viewport_info`

Query the full list of available viewport commands and their descriptions.
Useful for auto-discovery by remote clients.

**Request** (any client → branchShredder):

```json
{
  "id": "uuid-v4",
  "type": "viewport_info",
  "source": "mobileApp",
  "target": "branchShredder",
  "timestamp": "2026-04-30T12:00:00Z",
  "flags": {},
  "payload": {}
}
```

**Response**:

```json
{
  "type": "viewport_info",
  "payload": {
    "status": "complete",
    "commands": {
      "Move": {
        "description": "Pan the viewport by [dx, dy] offset in scene coordinates.",
        "value": "[number, number]",
        "example": {"Move": [10, -15]}
      },
      "zoom": {
        "description": "Multiply the current zoom level by the given factor. Values < 1 zoom out, values > 1 zoom in (e.g. 0.98 = zoom out 2%).",
        "value": "number",
        "example": {"zoom": 0.98}
      },
      "center": {
        "description": "Center the viewport on the given absolute [x, y] scene position.",
        "value": "[number, number]",
        "example": {"center": [0, 0]}
      },
      "center_node": {
        "description": "Center the viewport on the node with the given node ID.",
        "value": "string (nodeId)",
        "example": {"center_node": "abc123"}
      },
      "viewport": {
        "description": "Control viewport rendering. \"Render\" captures a PNG snapshot of the current viewport.",
        "values": ["Render"],
        "example": {"viewport": "Render"}
      },
      "output": {
        "description": "Set the output destination for a rendered image.",
        "values": ["WebSocket"],
        "example": {"output": "WebSocket"}
      },
      "width": {
        "description": "Maximum output image width in pixels (aspect ratio preserved).",
        "value": "number",
        "example": {"width": 1280}
      },
      "height": {
        "description": "Maximum output image height in pixels (aspect ratio preserved).",
        "value": "number",
        "example": {"height": 720}
      }
    },
    "messageTypes": {
      "viewport": "Execute a command pipeline. Send a list of command objects; include {\"viewport\": \"Render\"} to receive a PNG in the response.",
      "viewport_snapshot": "Convenience shorthand: optionally centre on nodeId, then capture and return a PNG.",
      "viewport_info": "Return this command reference."
    },
    "pipelineExample": [
      {"Move": [10, -15]},
      {"zoom": 0.98},
      {"viewport": "Render", "output": "WebSocket"}
    ]
  }
}
```

---

## Image Encoding

All PNG images returned over WebSocket are **base64-encoded** and carried in
the `"image"` field of the response payload.  The `"format"` field is always
`"png"`.

Decoding example (JavaScript):

```js
const bytes = Uint8Array.from(atob(payload.image), c => c.charCodeAt(0));
const blob  = new Blob([bytes], { type: "image/png" });
const url   = URL.createObjectURL(blob);
```

Decoding example (Python):

```python
import base64
png_bytes = base64.b64decode(payload["image"])
```

---

## Registered Capabilities

The full capability list that branchShredder advertises in its `register`
message:

```json
[
  "edit_story",
  "llm_chat",
  "query_nodes",
  "find_nodes",
  "get_node",
  "update_node",
  "system_prompt",
  "system",
  "viewport",
  "viewport_snapshot",
  "viewport_info"
]
```
