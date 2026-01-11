# HackVR Protocol Draft (refined, non-normative)

**Last edited:** 2026-01-10 17:26 (Europe/Berlin)

This document compiles the current working shape of the HackVR protocol. It is intentionally **not** normative yet, and some topics are explicitly left open.

---

## 1) Intent and philosophy

HackVR is a lightweight, stream-based protocol for connecting a **HackVR viewer (client)** to a **HackVR host (server)** that streams an interactive 3D scene.

Goals:

- **Low barrier to creation:** a server can generate worlds by writing lines to a stream.
- **Server-authoritative world state:** the server owns scene state; the client renders and reports user interactions.
- **Hyperlinkable worlds:** objects can link to other worlds.
- **Minimal primitives, lots of composition:** geometries + objects + billboards + verbs (“intents”) + picking/raycast input.
- **Optimistic by design:** invalid commands, missing entities, or missing assets should degrade gracefully (ignore, show placeholders) rather than fail hard.

Non-goals:

- **No keyframe animation system:** only best-effort transform transitions.
- **No continuous interaction primitives:** no drag/hold/analog streams; interactions are discrete events (taps, intents, text submission, ray input).

### 1.1 Conceptual operations vs exact state

HackVR operations are meant to target **semantic concepts**, not perfectly tracked low-level state.

- **Tags** describe *what something represents* (e.g., `door-main`, `enemy-goblin-03`) rather than triangle indices.
- Servers are encouraged to treat the scene like a declarative UI: “remove everything tagged `door-*`” and then “add the new `door-*` triangles,” without relying on or querying exact client-side geometry state.

### 1.2 Coordinate system

Coordinate system: **right-handed OpenGL convention** (X right, Y up, Z forward is -Z).

---

## 2) Transport, framing, and default HTTP upgrade path

### 2.1 Byte stream + line protocol

HackVR runs over any bidirectional byte stream.

- The stream is split into **CRLF-terminated lines**.
- Each line is a single command with **TAB-separated** arguments.
- Text is **UTF-8**.

Control characters are forbidden except:

- **TAB** (argument separator)
- **LF** (may appear *inside* a parameter to represent a newline)

#### 2.1.1 Formal grammar (EBNF)

Terminals:

- `CR` = U+000D
- `LF` = U+000A
- `TAB` = U+0009

EBNF:

```
stream    = { command } ;

command   = name , { TAB , param } , CR , LF ;

name      = { name_char } ;
param     = { param_char } ;

(* name_char disallows all Cc control characters (including LF). *)
name_char = ? any Unicode scalar value satisfying: (char not-in Cc) ? ;

(* param_char disallows all Cc control characters, with the special exception that LF is allowed. *)
param_char = ? any Unicode scalar value satisfying:
               (char == LF) OR (char not-in Cc) ? ;
```

Additional notes:

- `name` should be **non-empty**.
- `TAB` is a separator, so it cannot appear inside `name` or `param`.
- `CR` is not permitted anywhere except as part of the line terminator `CRLF`.
- Because `CR` is forbidden inside `name`/`param`, `CRLF` is an unambiguous command terminator; a bare `LF` does **not** terminate a command.

#### 2.1.2 Escaping

No escaping is available.

- You cannot encode a literal `TAB` or `CR` inside a parameter.
- You can encode multi-line text by including `LF` inside a parameter.

#### 2.1.3 End-of-stream behavior

If the stream ends:

- The viewer **must keep showing the current scene**.
- The viewer **must inform the user** that the connection was closed.
- If a session token was provided, the viewer **may offer automatic session resumption**.
- If no token was provided, the viewer **may offer a reconnect**.

### 2.2 URL schemes

- `hackvr://` (non-TLS)
- `hackvrs://` (TLS)

### 2.3 Default network path: HTTP/1.1 Upgrade

HackVR can be negotiated via HTTP/1.1 `Upgrade: hackvr` (conceptually similar to WebSockets).

Example client request:

```http
GET /world HTTP/1.1
Host: example.com
Connection: upgrade
Upgrade: hackvr
```

After a successful upgrade, the connection switches to the HackVR line protocol.

---

## 3) Commands

### Conventions

- `<name:type>` denotes a typed argument.
- `<name:[]type>` means the argument supports **selectors/globbing** (see **3.8 Selectors and globbing**).
- `[...]` optional, `{...}` repeated 0+ times.

Optional parameters may be:

- **Omitted** (fewer parameters in the command)
- **Present but empty** (consecutive TABs)

Example: the following all match `foo [<bar:zstring>] [<bam:zstring>]`:

- `foo<CR><LF>`
- `foo<TAB><CR><LF>`
- `foo<TAB><TAB><CR><LF>`

Mappings:

- `foo<CR><LF>` → `bar=null`, `bam=null`
- `foo<TAB><CR><LF>` → `bar=""`, `bam=null`
- `foo<TAB><TAB><CR><LF>` → `bar=""`, `bam=""`

Direction:

- **S→C** server to client
- **C→S** client to server
- **↔** either direction

### 3.1 Chat

- **↔** `chat [<user:userid>] <message:string>`
  - Server→client must include a user.
  - Client→server may use an empty user.

### 3.2 Authentication and sessions

#### 3.2.1 Overview

This is an optional identity and session layer intended to be "good enough" for hobby worlds.

Concepts:

- A connection may have an assigned `userid` (including `$anonymous`), and it may change over time.
- A `userid` may be protected by an identity.
- A session token can be established with or without a stable `userid`.
- Authentication implies a `userid` (i.e., there is nothing to authenticate without a claimed `userid`).

In other words: `userid`, authentication, and session tokens are related but orthogonal.

Security notes:

- Without TLS (`hackvrs://`), the protocol provides no confidentiality and is vulnerable to active MITM proxying.
- The primary goal is to avoid passwords and to minimize the impact of a compromised server implementation.

Auth model:

- A `userid` is bound to an Ed25519 public key (stored server-side as a `(userid, pubkey)` tuple).
- Authentication is a challenge/response signature over a server-provided nonce.

Constraints:

- `$anonymous` is a reserved `userid` value and can be used with session tokens (no stable username).
- Session tokens must not be persistet to disk and may live in the server process only.
  - If still required by implementation, only a hash of the token shall be stored.

Control flow (typical):

- The server may ask for a name via `request-user`. The viewer may also proactively send `set-user` (IRC-style).
- After `set-user`, the server either:
  - accepts immediately via `accept-user` (unprotected name), or
  - challenges via `request-authentication` and then accepts/rejects based on `authenticate`, or
  - rejects via `reject-user`.
- `resume-session` is independent of naming; the server may accept, reject, or require re-authentication before accepting.

#### 3.2.2 Commands

- **S→C** `request-user [<prompt:zstring>]`
  - Ask the viewer to provide or change a `userid` for this connection.
  - `prompt` is viewer UI text (may be empty).

- **C→S** `set-user <user:userid>`
  - Attempts to set (or change) the `userid` for the connection.
  - The server responds with `request-authentication`, `accept-user`, or `reject-user`.
  - If a user authentication was already established, this command shall invalidate that authentication in any case.
  - This command always invalidates a previously established session token provided by `accept-user`.
  - If user is `$anonymous`, the server must always respond with `accept-user`.

- **S→C** `request-authentication <user:userid> <nonce:bytes[16]>`
  - Requests proof of key ownership for `user`.
  - `nonce` must be generated from a cryptographic randomness source and must be single-use.
  - The server must invalidate the nonce after 60 seconds.
  - Invalidates any previous `request-authentication` including their `nonce`.

- **C→S** `authenticate <user:userid> <signature:bytes[64]>`
  - `signature` is an Ed25519 signature over the UTF-8 string `hackvr-auth-v1:<user>:<nonce>`.
    - `<user>` and `<nonce>` must match the last `request-authentication` for that connection.
    - `<nonce>` is the hex-encoded string as seen in `request-authentication` and must use the same upper/lower case text.

- **S→C** `accept-user <user:userid> [<session-token:string>]`
  - Indicates that `user` is accepted for the connection.
  - If provided, `session-token` is an opaque bearer token the viewer may store to resume after a connection loss.
  - If no `session-token` is provided, the session cannot be resumed by `resume-session`.
  - Token guidance: cryptographically random (128+ bits) and time-limited (e.g., ~1 hour).
  - The server may send `accept-user` again to rotate/refresh the token.
  - `accept-user $anonymous <session-token:string>` can be used to provide resumable sessions without a stable `userid`.

- **S→C** `reject-user <user:userid> [<reason:zstring>]`
  - Rejects `user` for the connection (naming, authentication attempt, or session resumption).
  - If authentication is enabled, the `reason` should be non-specific (avoid “invalid user” vs “invalid signature”).

- **C→S** `resume-session <user:userid> <session-token:string>`
  - Requests resumption of a previous session.
  - The server may require re-authentication via `request-authentication`.

### 3.3 Graphical Interface

#### 3.3.1 Text Input

- **S→C** `request-input <id:input> <prompt:string> [<default:string>]`
  - Viewer shows a modal text input box.

- **↔** `cancel-input <id:input>`
  - Cancels a pending input request.
  - Viewer: closes the modal if it is still open.
  - Server: should ignore if the input was already completed.

- **C→S** `send-input <id:input> <text:zstring>`
  - Sends the entered text.
  - Empty text is allowed and does **not** mean cancel.
  - If a viewer supports “cancel”, it should use `cancel-input`.

#### 3.3.2 Banner

- **S→C** `set-banner <text:string> [<t:float>]`
  - Show informational text to the user.
  - Empty text clears.
  - If `t` is provided, auto-hide after `t` seconds.

### 3.4 World Interaction

#### 3.4.1 Object Interaction

Client-originated interaction events do **not** use selectors/globbing.

- **C→S** `tap-object <obj:object> <kind:tapkind> <tag:tag>`
  - Reports a pick on `<obj>` at the semantic triangle tag.
  - Tapping always targets **user-visible geometry** (what the viewer is actually rendering).
  - If the hit triangle tag is empty (unreferenceable), the viewer should treat it as non-interactive (i.e., do not send `tap-object`).

- **C→S** `tell-object <obj:object> <text:zstring>`
  - Text sent to an object marked `textinput`.
  - Text may be empty.

#### 3.4.2 Intents (verbs / actions)

Default intents always exist:

`forward back left right up down stop`

Additional intents can be defined dynamically:

- **S→C** `create-intent <id:intent> <label:string>`
  - Add an extra intent the viewer can present (button, menu, keybind, radial menu, etc.).
- **S→C** `destroy-intent <id:intent>`
  - Remove a previously created additional intent.

Triggering an intent:

- **C→S** `intent <id:intent> <view-dir:vec3>`
  - User triggered an intent; includes current view direction so the server can interpret it.
  - Intents are **semantic**: the server chooses whether an intent behaves as impulse, state change, menu navigation, etc.

#### 3.4.3 Raycast mode (directional input)

HackVR has two interaction modes:

- **Picking mode (standard):** the viewer performs object/tag picking and sends `tap-object`.
- **Raycast mode (directional):** the viewer gathers a ray and sends `raycast`.

Raycast mode is a **temporary override** of picking mode: the server requests it, the user produces one ray (or cancels), and the viewer returns to picking mode.

Raycasts do **not** have a “hit world.” They merely inform the server of **directional input**; the viewer does not compute intersections and does not send hit results.

- **S→C** `raycast-request`
  - Enter raycast mode (viewer shows a crosshair/cursor; disables object/tag picking UI).
- **↔** `raycast-cancel`
  - Exit raycast mode without selection.
  - C→S: user canceled the selection.
  - S→C: server canceled a pending request.
- **C→S** `raycast <origin:vec3> <dir:vec3>`
  - User clicked while in raycast mode; viewer sends ray origin (camera position) and direction.
  - The click terminates raycast mode on the client.

### 3.5 Geometry management

Geometries are a **reusable visual representation** that can be attached to objects.

- A geometry is identified by `<id:geom>`.
- A geometry’s concrete kind is defined by how it was created (triangle soup vs text billboard vs image billboard).
- There are no geometry queries, so servers should maintain canonical state for runtime edits.

Predefined:

- `geom` **`$global`** exists.

Lifecycle:

- **S→C** `create-geometry <id:[]geom>`
  - Creates a **triangle soup** geometry (the default geometry kind).
- **S→C** `destroy-geometry <id:[]geom>`

#### 3.5.1 Triangle Soups (default geometry)

Triangle soups are the default geometry type.

Triangle creation (tag-aware):

- **S→C** `add-triangle-list  <id:[]geom> <tag:tag> { <color:color> <p0:vec3> <p1:vec3> <p2:vec3> }`
- **S→C** `add-triangle-strip <id:[]geom> <tag:tag> <color:color> <p0:vec3> <p1:vec3> <p2:vec3> { <pos:vec3> }`
- **S→C** `add-triangle-fan   <id:[]geom> <tag:tag> <color:color> <p0:vec3> <p1:vec3> <p2:vec3> { <pos:vec3> }`

Tag semantics:

- Tags are scoped to a geometry.
- Tags are **kebab-case strings** intended to be self-documenting (`door-entrance`, `enemy-goblin-03`, `ui-button-start`).
- Empty tag means **unreferenceable** (cannot be tapped, cannot be deleted).
- Triangles with the same tag are semantically identical; no triangle index exists at the protocol level.

Triangle removal (by tag match / selector):

- **S→C** `remove-triangles <id:[]geom> <tag:[]tag>`
  - Removes all triangles in `<id>` whose tag matches `<tag>`.

Picking/occlusion note:

- Tapping always targets **user-visible geometry**.
- Hit priority is front-to-back by depth.
- Tagged triangles behind untagged, fully opaque geometry are not clickable.

#### 3.5.2 Text Billboards

Text billboards are flat rectangles rendered in the world.

- **S→C** `create-text-geometry <id:[]geom> <size:vec2> <font-uri:string> <font-sha256:bytes[32]> <text:string> [<anchor:anchor>] [<billboard:billboard>]`

Defaults:

- `anchor` defaults to `center-center`.
- `billboard` defaults to `fixed`.

Text fitting:

- The viewer should render text so it **fits inside** the billboard rectangle ("contain").

Billboard hit-testing:

- Billboards are always treated like **two triangles forming a rectangle**.
- Billboards are **never hit-test transparent**.

Mutable text properties (common updates):

- **S→C** `set-text-property <id:[]geom> <property:string> <value:string>`
  - Common properties:
    - `text` (string)
    - `color` (`#RRGGBB`)

Guidance:

- For complex changes (font, billboard mode, anchor, sizing model), servers should destroy and recreate the text geometry.

#### 3.5.3 Image Billboards

Image billboards are flat rectangles rendered in the world.

- **S→C** `create-sprite-geometry <id:[]geom> <size:vec2> <uri:string> <sha256:bytes[32]> [<size-mode:sizemode>] [<anchor:anchor>] [<billboard:billboard>]`

Defaults:

- `size-mode` defaults to `stretch`.
- `anchor` defaults to `center-center`.
- `billboard` defaults to `fixed`.

Size mode semantics:

- `stretch`: stretch to exactly fill `size`.
- `cover`: preserve aspect ratio; fill `size` completely; crop overflow.
- `contain`: preserve aspect ratio; fit entirely within `size`.
- `fixed-width`: preserve aspect ratio; width = `size.x`, height derived.
- `fixed-height`: preserve aspect ratio; height = `size.y`, width derived.

Billboard hit-testing:

- Billboards are always treated like **two triangles forming a rectangle**.
- Billboards are **never hit-test transparent**.

Asset semantics:

- Hash is over downloaded bytes.
- Failure or hash mismatch displays an error placeholder.

Depth testing:

- Billboards depth-test like opaque geometry.

### 3.6 Object management (scene graph)

Objects have transform (position/orientation/scale) and may reference a geometry.

Predefined:

- `object` **`$global`** exists at origin and has `$global` geometry attached.
- `$global` is the **scene graph root** and **cannot be reparented**.

Default parenting:

- Unless otherwise specified, newly created objects are children of **`$global`**.

Lifecycle and hierarchy:

- **S→C** `create-object <obj:[]object> [<g:geom>]`
- **S→C** `destroy-object <obj:[]object>`
- **S→C** `add-child <parent:object> <child:[]object> [<space:string>]`
  - `space` is `world` (default) or `local`.

Geometry attachment:

- **S→C** `set-object-geometry <obj:[]object> <g:geom>`
  - Exactly one geometry is attached per object.

Properties:

- **S→C** `set-object-property <obj:[]object> <property:string> <value:string>`
  - Common properties:
    - `href` (hyperlink)
    - `clickable` (`true/false`)
    - `textinput` (`true/false`)

Navigation security (for `href`):

- Viewers **must require explicit user confirmation** before navigating to an `href`.
- Viewers should clearly display the full target (including scheme) during confirmation.

Transforms (with optional transition):

- **S→C** `set-object-transform <obj:[]object> [<pos:vec3>] [<rot:euler>] [<scale:vec3>] [<t:float>]`

Transition semantics:

- Purpose: **best-effort visual smoothing**, not simulation.
- Time base: viewer monotonic clock; no server timestamps.
- Channels are independent (pos/rot/scale).
- Updating a channel interrupts that channel and restarts from its current value.
- Omitting a channel means its existing transition continues.
- Guarantee: at the end of duration `t`, the object will be at the target transform.
- During transition, motion is “close enough” for visual purposes; small drift due to jitter is acceptable.
- Drift is bounded by the **longest active transition duration** (bounded, not cumulative).

Rotation semantics:

- `rot:euler` is authoring-friendly Euler angles.
- Interpolation is performed in quaternion space derived from Euler.
- Exact Euler axis/order/units are open topics.

### 3.7 Views and camera control

HackVR does not expose named views. The server directly sets the viewer’s camera pose.

- **S→C** `set-view [<pos:vec3>] [<view-dir:vec3>] [<duration:float>]`
  - Any omitted field remains unchanged.
  - If `duration` is provided, transition over `duration` seconds.
  - If omitted, change immediately.

Free-look control (disjoint from `set-view`):

- **S→C** `enable-free-look <enabled:bool>`
  - When enabled, the viewer may allow immediate local pan/tilt rotation (“free look”).
  - When disabled, the viewer should not allow free-look rotation.

Background:

- **S→C** `set-background-color <color:color>`
  - Sets the viewer background color for the world.
  - Default background color is `#000080`.

---

### 3.8 Selectors and globbing

HackVR supports selector syntax for **batching** and **semantic matching**.

Selectors are supported for:

- `object`, `geom`, and `tag` parameters (marked as `[]` in command signatures)

Selectors are **not** supported for:

- `userid`, `intent`, `input`

General operation:

- A selector expands to **zero or more concrete values**.
- If a selector expands to zero values, the command becomes a no-op.
- **No deterministic expansion order is required**; commands must not depend on selector expansion order.

Multiple selector parameters:

- If a command contains multiple selector parameters, each selector is expanded independently and the command is applied to the **cartesian product** of expansions.

Creation + selectors:

- For commands that *create* entities, selectors are allowed **only as expansions**, not as wildcards.
  - Allowed: `{a,b,c}`, `{0..10}`, `{00..10}`
  - Not allowed in create commands: `*` or `?`
- If a create command targets an ID that already exists, the receiver should **re-create** it (replace existing with a fresh instance).

Selector-friendly naming:

- IDs and tags are kebab-case “parts” separated by `-`, e.g. `cheese-01-fancypants`.
- `$global` remains reserved.

Globbing syntax:

- `*` matches zero or more kebab parts
  - `cheese-*-done` matches `cheese-done`, `cheese-01-done`, `cheese-01-a-done`, ...
- `?` matches exactly one kebab part
  - `cheese-?-done` matches `cheese-01-done` but not `cheese-done`
- `{a,b,c}` expands to variants
- `{0..10}` expands to `0..10`
- `{00..10}` expands to `00..10` (zero-padded width inferred from endpoints)

---

## 4) Types

### 4.1 Primitive types

- **string**: UTF-8 text. Must have at least a single character. Empty is only allowed if optional.
- **zstring**: UTF-8 text. May be empty.
- **float**: decimal floating point, must be non-empty.
- **bool**: `true` or `false`, must be non-empty.
- **int**: decimal integer, must be non-empty.
- **vec2**: `(<x:float> <y:float>)`, must be non-empty.
- **vec3**: `(<x:float> <y:float> <z:float>)`, must be non-empty.
- **color**: `#RRGGBB` (24-bit), must be non-empty.
- **bytes**: hex-encoded bytes (even number of hex chars), must be non-empty.
- **bytes[N]**: fixed-length hex-encoded bytes of length N (2N hex chars), must be non-empty.

### 4.2 Optional parameter mapping

For an optional parameter `[<x:type>]`:

- If the parameter is **omitted**, it maps to **absent/null**.
- If the parameter is **present but empty**:
  - For `zstring`, it maps to the **empty string** `""`.
  - For all other types, it maps to **absent/null**.

### 4.3 Identifier types

- **userid** (regular string; not globbable)
- **object**
- **geom**
- **intent**
- **input** (token identifying a `request-input` / `send-input` exchange)

### 4.4 Structured/enumeration types

- **tag**: a kebab-case string identifier scoped to a geometry.
  - May be empty to mean “unreferenceable”.
- **euler**: a `vec3` interpreted as Euler angles (exact axis order/units TBD).
- **tapkind**: one of `{primary|secondary}`.
- **sizemode**: one of `{stretch|cover|contain|fixed-width|fixed-height}`.
- **billboard**: one of `{fixed|y|xy}`.
- **anchor**: one of `{top|center|bottom}-{left|center|right}`.

---

## 5) Error handling model (non-normative guidance)

HackVR is failure-permissive:

- Unknown/invalid commands: ignore.
- Missing IDs (unknown object/geom/intent): ignore.
- Missing assets or hash mismatch: show error placeholder and continue.
- Network interruption: the viewer may present a resume/reconnect option as described in **2.1.3**, but must continue showing the last scene.

Rationale:

- Matches the intended social/exploration “fun and leisure” use cases.
- Avoids leaking information via detailed error messages.

---

## 6) Implementation limits (anti-DoS guidance)

Clients should enforce reasonable soft limits (reference values):

- Selector expansion: **1,000 concrete command applications** maximum per command (after any multi-selector expansion)
- Triangle count per geometry: **100,000 triangles**
- Object count: **10,000 objects**
- Object nesting depth: **16 levels**
- Command rate: **1,000 commands/sec**

Specialized clients may tune these values.

---

## 7) Open topics to define properly

### Geometry and transforms

- Exact Euler axis/order/units and handedness/sign conventions.
- Interpolation edge cases: shortest-path rotation, scale interpolation details.

### Billboards

- Text layout details (wrapping, alignment, overflow) beyond the “fit/contain” requirement.
- Text styling model (links, underline, outline, etc.), if any is protocol-level.

### Assets, security, and navigation

- Transport profiles for assets (exact allowed schemes per world source).
- Caching strategy and optional `invalidate-url` command semantics.
- Sandboxing boundaries for navigation and cross-world capabilities.

### Interaction UX

- Viewer presentation guidelines for intents (menus, keybinds, ordering).
- `request-input` UX details (e.g., whether cancellation must be possible).
- Rate limiting recommendations for `set-banner` and other UI-affecting commands.

### Selectors and batching

- Exactly which commands accept selectors (current stance: commands that take `object`, `geom`, or `tag` parameters are marked with `[]`).
