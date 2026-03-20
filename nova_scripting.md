# Nova Node Scripting Reference

This file documents the scripting language understood by **Nova**, branchShredder's AI
assistant, for creating and wiring nodes in the story graph.

It is automatically loaded and appended to Nova's system prompt at startup, so changes
here take immediate effect without touching source code.

This file can also be supplied as a **system-prompt supplement** to any external LLM
that needs to generate branchShredder-compatible node XML (e.g. a network-connected LLM
being fed story context via procMessenger).

---

## Creating Nodes

To create nodes, emit one or more XML tags on their own lines, separate from prose:

```xml
<create_node title="Node Title" type="NodeType" nodePath="Parent > Child">
Full Markdown content here.
</create_node>
```

### Attributes

| Attribute   | Required | Description |
|-------------|----------|-------------|
| `title`     | yes      | Node name. Should be unique. If modifying an existing node add "modified" to the name. |
| `type`      | yes      | One of the node types listed below. |
| `nodePath`  | no       | Path of an existing node to connect as input (see *nodePath* section below). |

### Node Types

| Type        | Purpose |
|-------------|---------|
| `DIALOGUE`  | Characters speaking — lines of in-world dialogue |
| `CHARACTER` | Bio/traits/backstory for a named character |
| `NOTE`      | Author private notes not part of the story world |
| `EVENT`     | Plot points and story events |
| `INFO`      | Lore, worldbuilding, and reference material |
| `SECRET`    | Hidden twists not shown to players |
| `START`     | Graph entry point |
| `END`       | Graph exit / conclusion point |
| `GLOBALS`   | Global variables used for branching logic |

### nodePath Attribute

The optional `nodePath` attribute connects the new node as a downstream output of an
existing node in the story graph.

Accepted values:
- **Full path** matching the "Story Graph Position" shown in context
  (e.g. `"Start > Chapter 1 > Scene A"`)
- **Node title** alone if it is unique in the graph (e.g. `"Scene A"`)
- **Title of a node created earlier** in the same response

Omit `nodePath` if all new nodes in the response share the same selected input node, or
if the node should stand alone with no connection.

---

## Markdown Content

Use rich Markdown inside `<create_node>` tags.  Give every node a meaningful title and
substantive content — the author will use and edit it directly.

Multiple `<create_node>` blocks per response are fine and encouraged when the request
naturally produces several related nodes (e.g. a scene and its participating characters).

---

## Examples

### Single dialogue node

```xml
<create_node title="Prologue - Tavern Greeting" type="DIALOGUE" nodePath="Start">
**Innkeeper:** "You look like you've walked from the edge of the world, stranger.
Room's two silver, and supper's extra."

**Player:** "How about information instead of coin?"
</create_node>
```

### Character with no upstream connection

```xml
<create_node title="Mira Ashford" type="CHARACTER">
## Mira Ashford — Rogue Artificer

**Age:** 28  **Origin:** Clockwork City of Verenthia

Mira is a disgraced guild engineer who now sells her skills to the highest bidder.
She speaks tersely, mistrusts authority, and has a soft spot for stray animals.

- **Strength:** Improvised gadgetry under pressure
- **Weakness:** Pride; will not admit when outmatched
</create_node>
```

### Chained lore / info nodes

```xml
<create_node title="The Shattered Compact" type="INFO" nodePath="Start">
Three hundred years ago the five kingdoms signed the Compact of Embers, agreeing to
share magical resources. It collapsed when the Ashveran king was assassinated at the
ratification ceremony — a crime never officially resolved.
</create_node>

<create_node title="Ashveran Succession Crisis" type="EVENT" nodePath="The Shattered Compact">
With the king dead and no heir declared, three noble houses each claimed the throne.
The resulting civil war lasted a decade and left the capital half-buried in rubble.
</create_node>
```
