# HackVR Protocol Draft (refined, non-normative)

**Last edited:** 2026-01-10 17:26 (Europe/Berlin)

This document compiles the current working shape of the HackVR protocol. It is intentionally **not** normative yet, and some topics are explicitly left open.

## 1) Intent and philosophy

HackVR is a lightweight, stream-based protocol for connecting a **HackVR viewer (client)** to a **HackVR host (server)** that streams an interactive 3D scene.

Goals:

- **Low barrier to creation:** a server can generate worlds by writing lines to a stream.
- **Server-authoritative world state:** the server owns scene state; the client renders and reports user interactions.
- **Hyperlinkable worlds:** objects can link to other worlds.
- **Minimal primitives, lots of composition:** geometries + objects + tracking + verbs (“intents”) + picking/raycast input.
- **Optimistic by design:** after connection establishment, invalid commands, missing entities, or missing assets should degrade gracefully (ignore, show placeholders) rather than fail hard.
- **Easy of server implementation:** This protocol lives by an ecosystem of different servers, worlds, games, presentations, ... Thus, a focus is set to make server implementations easy.

Non-goals:

- **No keyframe animation system:** only best-effort transform transitions.
- **No continuous interaction primitives:** no drag/hold/analog streams; interactions are discrete events (taps, intents, text submission, ray input).
- **No complex rendering setups:** Materials, transparency and effects are explicitly left out to simplify the mental model for server creators and ease the life of viewer implementors.
- **Viewer queries:** As the server is authorative, it has knowledge about all data present on the viewer. Viewers have no ability to manipulate the world, so queries which send world data from viewer to server are out of scope.

**Strict failure rules apply only during connection establishment handshakes** (raw `hackvr-hello` and HTTP Upgrade). After establishment, the protocol uses optimistic error handling.

### 1.1 Conceptual operations vs exact state

HackVR operations are meant to target **semantic concepts**, not perfectly tracked low-level state.

- **Tags** describe *what something represents* (e.g., `door-main`, `enemy-goblin-03`) rather than triangle indices.
- Servers are encouraged to treat the scene like a declarative UI: “remove everything tagged `door-*`” and then “add the new `door-*` triangles,” without relying on or querying exact client-side geometry state.
- Network latencies are accepted and should be expected. A server should not treat this as a "hard" realtime protocol.

### 1.2 Coordinate system

Coordinate system: **right-handed OpenGL convention**.

- +X is **right**
- +Y is **up**
- -Z is **forward**

Unless otherwise specified, all vectors are expressed in this world basis.

#### 1.2.1 Local basis at zero rotation

For both **objects** and the **camera**, the neutral (zero) orientation uses:

- Right   R₀ = (1, 0, 0)
- Up      U₀ = (0, 1, 0)
- Forward F₀ = (0, 0,-1)

Rotation commands define an orientation that transforms this local basis into world space.

## 2) Transport, framing, and default HTTP upgrade path

### 2.1 Byte stream + line protocol

HackVR runs over any bidirectional byte stream.

- The stream is split into **CRLF-terminated lines**.
- Each line is a single command with **TAB-separated** arguments.
- Text is **UTF-8**.

Control characters are forbidden except:

- **TAB** (argument separator)
- **LF** (may appear *inside* a parameter to represent a newline)

Lines with invalid UTF-8, stray CR, or other framing violations are **command errors** and shall be ignored after establishment.

Lines must not exceed 1024 bytes including the CR, LF line end. Overlong lines are a framing error and must not be parsed as commands.

Recovery after a frame parsing error (invalid encoding, line length limit exceeded, ...) shall be recovered by scanning for a CR, LF sequence and regular frame parsing shall resume afterwards.

#### 2.1.1 Formal grammar (EBNF)

Terminals:

- `CR` = U+000D
- `LF` = U+000A
- `TAB` = U+0009

EBNF:

```ebnf
stream    = { command } ;

command   = name , { TAB , param } , CR , LF ;

name      = name_char, { name_char } ;
param     = { param_char } ;

(* name_char disallows all Cc control characters (including LF). *)
name_char = ? any Unicode scalar value satisfying: (char not-in Cc) ? ;

(* param_char disallows all Cc control characters, with the special exception that LF is allowed. *)
param_char = ? any Unicode scalar value satisfying:
               (char == LF) OR (char not-in Cc) ? ;
```

Additional notes:

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
- The viewer **must not automatically reconnect** in any case.
- Any (re)connection attempt must be an explicit **user action**.

### 2.2 URL schemes

Normative mappings:

- `hackvr://` = raw TCP, unencrypted; HackVR starts after `hackvr-hello`.
- `hackvrs://` = raw TCP + TLS 1.2/1.3 or later; HackVR starts after TLS + `hackvr-hello`.
- `http+hackvr://` = HTTP/1.1 Upgrade over HTTP.
- `https+hackvr://` = HTTP/1.1 Upgrade over HTTPS.

### 2.3 Connection establishment — HTTP/1.1 Upgrade

HackVR can be negotiated via HTTP/1.1 `Upgrade: hackvr` (conceptually similar to WebSockets).

Example client request:

```http
GET /world HTTP/1.1
Host: example.com
Connection: upgrade
Upgrade: hackvr
HackVr-Version: v1
```

Required success criteria:

- Server responds with **`101 Switching Protocols`**.
- Response includes `Connection: upgrade` and `Upgrade: hackvr` (case-insensitive).

After a successful upgrade, the HackVR command stream begins **immediately after the HTTP headers** (after the blank line).

Failure handling:

- Viewer must display failure to the user.
- If the server returns **2xx**, the viewer should display the plaintext response body for debugging.

Version signaling:

- The protocol version is carried via the HTTP header `HackVr-Version: v1`.
- HTTP profile currently pins to `v1` (negotiation is defined in the raw handshake section).

Redirect binding:

- Session/origin binding for HTTP uses **the request that finally opens the HackVR connection** (the final request that successfully upgraded).

### 2.4 Connection establishment — raw handshake (`hackvr-hello`)

Raw `hackvr(s)://` connections perform a strict handshake before any other commands.

Handshake schema:

- **C→S** `hackvr-hello <max-version:version> <uri:uri> [<session-token:session-token>]`
  - `uri` must not contain a fragment; viewers may extract the fragment as a session token before connecting.
- **S→C** `hackvr-hello <max-version:version>`

`hackvr-hello` uses regular command syntax, but does not count towards the set of HackVR commands. It is only part of the hackvr(s):// handshake.

Version negotiation:

- Versions match `/v[1-9][0-9]*/`; parse the integer suffix and choose the **minimum** of client/server.
- Parse failure or unsupported effective version => close connection; viewer should inform user, server may log.

Strictness:

- Both sides must send `hackvr-hello` immediately after connect.
- The first received line must be `hackvr-hello`; otherwise close.
- No other commands are allowed pre-hello.
- After the hello exchange, the protocol enters optimistic mode.

Connect-time session token behavior:

- If a client hello includes a `session-token`, it is treated as if the client sent `resume-session <token>` as the first client action.

## 3) Commands

### Conventions

- `<name:type>` denotes a typed argument.
- `<name:[]type>` means the argument supports **selectors/globbing** (see **3.8 Selectors and globbing**).
- `[...]` optional, `{...}` repeated 0+ times.

The following rules also apply:

- If the number of parameters available **on-wire** is less than the number of parameters, the missing parameters must be interpreted as if they were sent empty.

This means that optional parameters may be:

- **Omitted** (fewer parameters in the command)
- **Present but empty** (consecutive TABs)

Example: the following all match `foo [<bar:string>] [<bam:string>]`:

| On-wire Data              | Parsed Array          | `bar`  | `bam`  |
|---------------------------|-----------------------|--------|--------|
| `foo<CR><LF>`             | `[ "foo" ]`           | `null` | `null` |
| `foo<TAB><CR><LF>`        | `[ "foo", "" ]`       | `null` | `null` |
| `foo<TAB>x<CR><LF>`       | `[ "foo", "x" ]`      | `x`    | `null` |
| `foo<TAB><TAB><CR><LF>`   | `[ "foo", "",  "" ]`  | `null` | `null` |
| `foo<TAB>x<TAB><CR><LF>`  | `[ "foo", "x", "" ]`  | `x`    | `null` |
| `foo<TAB><TAB>y<CR><LF>`  | `[ "foo", "",  "y" ]` | `null` | `y`    |
| `foo<TAB>x<TAB>y<CR><LF>` | `[ "foo", "x", "y" ]` | `x`    | `y`    |

Direction:

- **S→C** server to client
- **C→S** client to server
- **↔** either direction

Type validation may be stricter than framing. For example, framing permits LF inside parameters, but types such as `userid` and `uri` forbid LF. Type violations are command errors (ignored after establishment).

After establishment, unknown/invalid commands are ignored (optimistic model), not connection-fatal.

### 3.1 Chat

Chat messages shall work like typical chat systems.

- **S→C** `chat <user:userid> <message:string>`
  - Notifies the viewer of a chat message
  - Server must always include user.
- **C→S** `chat <message:string>`
  - Notifies the server that the user wants to send a message.
  - No user required as the server must know the user context.

`message` must be a non-empty for both server and viewer messages, as empty chat messages contain no relevant information.

### 3.2 Authentication and sessions

#### 3.2.1 Overview

This is an optional identity and session layer intended to be "good enough" for hobby worlds.

Concepts:

- A connection always has an assigned `userid` (including `$anonymous`), and it may change over time.
- A `userid` may be protected by an identity.
- Session tokens are **session identifiers/context hints**, not authentication credentials.
- Authentication implies a `userid` (i.e., there is nothing to authenticate without a claimed `userid`).

Security notes:

- Without TLS (`hackvrs://`), the protocol provides no confidentiality and is vulnerable to active MITM proxying.
- The primary goal is to avoid passwords and to minimize the impact of a compromised server implementation.

Auth model:

- A `userid` is bound to an Ed25519 public key (stored server-side as a `(userid, pubkey)` tuple).
- Authentication is a challenge/response signature over a server-provided nonce.

Constraints:

- `$anonymous` is a reserved `userid` value
- `$anonymous` is the `userid` active when no other `userid` is accepted.

#### 3.2.2 Authentication commands

- **S→C** `request-user [<prompt:zstring>]`
  - Ask the viewer to provide or change a `userid` for this connection.
  - `prompt` is viewer UI text (may be empty).
  - This command initializes the authentication workflow.
    - No other command of this group may be sent before `request-user`.

- **C→S** `set-user <user:userid>`
  - Attempts to set (or change) the `userid` for the connection.
  - The server responds with `request-authentication`, `accept-user`, or `reject-user`.
  - If `user` is `$anonymous`, the server must respond with `accept-user`.
  - This command must only be sent after a `request-user` was received.

- **S→C** `request-authentication <user:userid> <nonce:bytes[16]>`
  - Requests proof of key ownership for `user`.
  - `nonce` must be generated from a cryptographic randomness source and must be single-use.
  - The server must invalidate the nonce after 60 seconds.
  - Invalidates any previous `request-authentication` including their `nonce`.
  - `nonce` may be upper/lowercase hex on wire; receivers accept both.
  - This command must only be sent after `set-user` was received.

- **C→S** `authenticate <user:userid> <signature:bytes[64]>`
  - `signature` is an Ed25519 signature over the UTF-8 string `hackvr-auth-v1:<user>:<nonce>`.
    - `<user>` and `<nonce>` must match the last `request-authentication` for that connection.
    - `<nonce>` must be **canonical lowercase hex** when used in the signing string.
  - No string normalization occurs; viewers sign exactly what they received, after canonical lowercase conversion of `nonce`.
  - `nonce` is invalidated by this command.
  - Must be followed by either `accept-user` or `reject-user`.
    - Non-normative: If the server does not respond with either command, the viewer must assume the login process is still in process.
  - This command must only be sent after a `request-authentication` was received.

- **S→C** `accept-user <user:userid>`
  - Indicates that `user` is accepted for the connection.
  - After this command:
    - The server might send `request-user` again.

- **S→C** `reject-user <user:userid> [<reason:zstring>]`
  - Rejects `user` for the connection (naming or authentication attempt).
  - If authentication is enabled, the `reason` should be non-specific (avoid “invalid user” vs “invalid signature”).
  - This command resets the active `userid` to `$anonymous`.
  - After this command:
    - The server might send `request-user` again.

Command Sequence:

```plain
<IDLE>                 → request-user
request-user           → set-user
set-user               → request-authentication | accept-user | reject-user
request-authentication → authenticate
authenticate           → accept-user | reject-user
accept-user            → <IDLE>
reject-user            → <IDLE>
```

#### 3.2.3 Sessions (non-authentication)

Session tokens identify server-side state (think “savegame id”), not identity.

- Tokens may be shared across viewers.
- Tokens are **not invalidated by use**; multiple connections may resume the same token if server allows (e.g., lobby/instance).
- The server must not treat possession of a token as authentication; access control requires separate logic.
- Tokens may expire; servers should revoke when feasible.

Commands:

- **S→C** `announce-session <token:session-token>`
  - Sets/refreshes the token associated with the current connection context.
  - If token differs from the previously announced token for this connection, the previously announced token becomes invalid (revoked for this connection).
  - If token is the same as previously announced, refreshes/extends lifetime.
- **S→C** `revoke-session <token:session-token>`
  - Informs viewer that token is no longer valid/usable (server/world-wide invalidity).
- **C→S** `resume-session <token:session-token>`
  - Semantics are server-defined: may restore state, switch lobbies, be idempotent or not; client should rely on scene updates and `set-banner` for user feedback.

Establishment-time token carriage:

- For raw `hackvr(s)://`: optional session token parameter in client `hackvr-hello`.
- For HTTP upgrade: HTTP request header `HackVr-Session: <session-token>`.
- An establishment token is treated as if the client sent `resume-session <token>` as the **first client action**.

World-state baseline:

- The protocol assumes empty/default world state on connection.
- Session resumption does not assume any client-retained scene; server must recreate scene explicitly if desired.

Context scope:

- “Connection/session context” means the lifetime of the transport connection (open→close).
- Rotation/refresh semantics for `announce-session` are defined with respect to the connection context.
- `resume-session` does not create a new context.

Token encoding rules:

- Session tokens are base64url without padding, decode to exactly 32 bytes, encoded length 43 chars, compared by decoded bytes.

URL fragment as session token (viewer convenience):

- For HackVR URLs, fragment `#<token>` is interpreted as a session token and injected into the connect-time token parameter/header.
- Fragment is not transmitted as part of `uri` on wire; it is viewer-side parsing only.

Session/origin binding:

- Session tokens are same-origin bound using handshake-derived `(domain, port, path, query)` for raw connections and `Host + request-target` for HTTP.
- URI fragments are ignored for binding.

### 3.3 Graphical Interface

#### 3.3.1 Text Input

- **S→C** `request-input <prompt:string> [<default:string>]`
  - Server requests text from the user.
  - `prompt` tells the user what is expected from them.
  - If `default` is given, it may be hinted to the user or be already prefilled.
  - A new `request-input` replaces any previous active request-input.
  - The viewer shall not clear the current user draft when replacing (keeps draft).
  - `request-input` is orthogonal to `request-user`; both may be active.

- **S→C** `cancel-input`
  - Cancels the previous `request-input` (idempotent; no-op if none active).

- **C→S** `send-input <text:zstring>`
  - Sends the entered text.
  - Empty text is allowed and does **not** mean cancel.
  - The command may only be sent while an input request is active.

Correlation between `request-input` and `send-input` is server-side only; there is no protocol correlation id.

Text input mode state:

- `request-input` sets `text_input_mode = true`.
- `cancel-input` sets `text_input_mode = false`.
- `send-input` must only be sent when `text_input_mode` was true; it sets `text_input_mode = false` before emitting.
- Multiple `request-input` do not queue text inputs; they just keep mode true until the text input is completed or cancelled.

#### 3.3.2 Banner

- **S→C** `set-banner [<text:string>] [<t:float>]`
  - Show informational text to the user.
  - If `text` is absent, the informational text is hidden.
  - If `t` is provided, auto-hide after `t` seconds (`t` must be ≥ 0).

### 3.4 World Interaction

#### 3.4.1 Object Interaction

Client-originated interaction events do **not** use selectors/globbing.

- **C→S** `tap-object <obj:object> <kind:tapkind> <tag:tag>`
  - Reports a pick on `<obj>` at the semantic triangle tag.
  - Tapping always targets **user-visible geometry** (what the viewer is actually rendering).
  - If the hit triangle tag is empty (unreferenceable), the viewer must not send `tap-object`.
  - Viewer must not send `tap-object` for objects with `clickable=false`.
  - For sprite geometries ($3.5.2 Sprite Geometries), the tag is the derived {X}-{Y} position tag; for triangle soups (§3.5.1 Triangle Soups) it is the semantic triangle tag.

- **C→S** `tell-object <obj:object> <text:zstring>`
  - Text sent to an object marked `textinput`.
  - Text may be empty.

- An object might have a `href` property set, which allow hyperlinking between worlds and from worlds to foreign content.
  - Viewer must confirm navigation and show full target including scheme.
  - Unknown schemes delegated to OS default handler; HackVR schemes open as worlds.

All three interactions (`tap-object`, `tell-object` and *open `href`*) are mutually exclusive *per interaction*. That means a single user action must never trigger more than a single interaction at once.

#### 3.4.2 Intents (verbs / actions)

> REWORD: Intents are the non-world interaction with the server.
>
> - Intents are **semantic**: the server chooses whether an intent behaves as impulse, state change, menu navigation, etc.
> - They must not be auto-repeated by a viewer

Default intents that are **predefined and initially present** on connect:

- `$forward`: "Move forward"
- `$back`: "Move backward"
- `$left`: "Move left"
- `$right`: "Move right"
- `$up`: "Move up"
- `$down`: "Move down"
- `$stop`: "Stop movement"

These intents may be destroyed and recreated. Viewers may display destroyed predefined intents as disabled UI controls for layout consistency, but must not emit `intent` for non-existent intents.

Additional intents can be defined dynamically:

- **S→C** `create-intent <id:intent> <label:string>`
  - Add an extra intent the viewer can present (button, menu, keybind, radial menu, etc.).
  - If an intent with the name `id` already exists, changes its label.
    - This also includes the predefined intents (upsert).
- **S→C** `destroy-intent <id:intent>`
  - Remove an intent.
  - This also includes the predefined intents.

Triggering an intent:

- **C→S** `intent <id:intent> <view-dir:vec3>`
  - User triggered an intent; includes current view direction so the server can interpret it.
  - `view-dir` is the **currently rendered viewing direction** in **global world coordinates** (includes free-look, tracking, etc.; i.e., what the user is actually facing).

#### 3.4.3 Raycast mode (directional input)

HackVR has two interaction modes:

- **Picking mode (standard):** the viewer performs object/tag picking and sends `tap-object`.
- **Raycast mode (directional):** the viewer gathers a ray and sends `raycast`.

Raycast mode is a **temporary override** of picking mode: the server requests it, the user produces one ray (or cancels), and the viewer returns to picking mode.

Raycasts do **not** have a “hit world.” They merely inform the server of **directional input**; the viewer does not compute intersections and does not send hit results.

Raycast mode state:

- `raycast-request` sets `raycast_mode = true` (idempotent).
- `raycast-cancel` sets `raycast_mode = false` (idempotent).
- `raycast` must only be sent when `raycast_mode` was true; it sets `raycast_mode = false` before emitting.
- Multiple `raycast-request` do not queue rays; they just keep mode true until one ray or cancel.

Commands:

- **S→C** `raycast-request`
  - Enter raycast mode (viewer shows a crosshair/cursor; disables object/tag picking UI).
- **↔** `raycast-cancel`
  - Exit raycast mode without selection.
  - C→S: user canceled the selection.
  - S→C: server canceled a pending request.
- **C→S** `raycast <origin:vec3> <dir:vec3>`
  - User clicked while in raycast mode; viewer sends ray origin (camera position) and direction.
  - The click terminates raycast mode on the viewer.
  - `origin` and `dir` are in global world coordinates.
    - `dir` is not required to be normalized. Servers may normalize if needed. If `dir` is the zero vector, the command is a **command error** and should be ignored.

### 3.5 Geometry management

Geometries are a **reusable visual representation** that can be attached to objects.

- A geometry is identified by `<id:geom>`.
- A geometry’s concrete kind is defined by how it was created (triangle soup vs text geometry vs sprite geometry).
- There are no geometry queries, so servers should maintain canonical state for runtime edits.
- Any `create-...` commmand that creates a geometry must fail if the geometry already exists.
  - Duplicate geometries are not allowed.

Predefined:

- `geom` **`$global`** exists.

Commands:

- **S→C** `destroy-geometry <g:[]geom>`
  - `g` cannot be `$global`.
  - If an object has `g` assigned, the objects geometry will be unset.

#### 3.5.1 Triangle Soups (default geometry)

Triangle soups are the default geometry type.

- **S→C** `create-geometry <g:[]geom>`
  - `g` cannot be `$global`.

Triangle creation (tag-aware):

- **S→C** `add-triangle-list  <id:[]geom> [<tag:tag>] { <color:color> <p0:vec3> <p1:vec3> <p2:vec3> }`
- **S→C** `add-triangle-strip <id:[]geom> [<tag:tag>] <color:color> <p0:vec3> <p1:vec3> <p2:vec3> { <pos:vec3> }`
- **S→C** `add-triangle-fan   <id:[]geom> [<tag:tag>] <color:color> <p0:vec3> <p1:vec3> <p2:vec3> { <pos:vec3> }`

Strip/fan construction:

- Triangle strip: each new vertex `pos` forms triangle `(seq[n-2], seq[n-1], pos)`.
- Triangle fan: each new vertex `pos` forms triangle `(seq[0], seq[n-1], pos)`.

Color semantics:

- `add-triangle-strip` and `add-triangle-fan` apply **one color per invocation** (single color for all triangles produced).
- If per-triangle color is needed, servers must use `add-triangle-list`.

Tag semantics:

- Tags are scoped to a geometry.
- Tags are **dash-grouped identifiers** intended to be self-documenting (`door-entrance`, `enemy-goblin-03`, `ui-button-start`).
- Absent tag means **unreferenceable** (cannot be tapped, cannot be deleted).
- Triangles with the same tag are semantically identical; no triangle index exists at the protocol level.

Triangle removal (by tag match / selector):

- **S→C** `remove-triangles <id:[]geom> <tag:[]tag>`
  - Removes all triangles in `<id>` whose tag matches `<tag>`.

Winding/culling/picking:

- Winding order does not matter; no backface culling.
- Triangles are visible and pickable from both sides.

Picking/occlusion note:

- Tapping always targets **user-visible geometry**.
- Hit priority is front-to-back by depth.
- Tagged triangles behind untagged, fully opaque geometry are not clickable.

Untagged permanence:

- Empty/missing tag is unreferenceable and intentionally non-removable/non-tappable.
- `remove-triangles` can only remove tagged triangles.
- Selector `*` matches all **tagged** triangles; untagged remain permanent.

#### 3.5.2 Sprite Geometries

Sprite geometries are flat rectangles rendered in the world.

They consist of two triangles that form a rectangle on the XY plane. Their origin is defined by an `anchor`.

When looking at the front of the sprite (so with a view direction of `(0 0 1)`), the coordinate system for 2D content is this:

- "top-left" is at `(-W/2, H/2, 0)` (assuming an `center-center` anchor).
- "bottom right" is at `(W/2, -H/2, 0)` (assuming an `center-center` anchor).

Hit-testing:

- Sprite geometries are always treated like **two triangles forming a rectangle**.
- They are **never hit-test transparent**.
- All sprite geometries have implicitly tagged surfaces:
  - When picked with `tap-object`, the viewer must derive in the form `{X}-{Y}` with
    - `X` being an integer between 0 (left edge) and 100 (right edge)
    - `Y` being an integer between 0 (top edge) and 100 (bottom edge)
  - The coordinates allow a server to derive which part of an image was clicked

Depth testing:

- Sprites depth-test like opaque geometry.
- For image rendering, alpha testing *may* be used for image geometries

#### 3.5.2.1 Text Geometries

Text geometries are sprites that display written text.

- **S→C** `create-text-geometry <id:[]geom> <size:vec2> <uri:uri> <sha256:bytes[32]> <text:string> [<anchor:anchor>]`
  - `id` cannot be `$global`.
  - `size` is in local unscaled coordinates.
  - (`uri`, `sha256`) is a font asset (see §6.1 Font Assets).
  - `text` is the text that shall be displayed on the geometry.
  - `anchor` defines the origin of the sprite (default: `center-center`).

Text fitting:

- The viewer should render text so it **fits inside** the rectangle ("contain").

Mutable text properties (typed):

- **S→C** `set-text-property <id:[]geom> <property:string> <value:any>`
  - `text: string` (non-empty)
  - `color: color` (default: `#000000`)
  - `background: color` (default: `#FFFFFF`)

Empty handling is based on the expected type (see `any` rules).

Guidance:

- For complex changes (font, anchor, sizing model), servers should destroy and recreate the text geometry.

#### 3.5.2.1 Image Geometries

Image geometries are sprites that display an image.

- **S→C** `create-sprite-geometry <id:[]geom> <size:vec2> <uri:uri> <sha256:bytes[32]> [<size-mode:sizemode>] [<anchor:anchor>]`
  - `id` cannot be `$global`.
  - `size` is in local unscaled coordinates.
  - (`uri`, `sha256`) is an image asset (see §6.2 Image Assets).
  - `size-mode` defines how the `size` may be adjusted depending on the image content (default: `stretch`).
  - `anchor` defines the origin of the sprite (default: `center-center`).

Size mode semantics:

- `stretch`: stretch to exactly fill `size`.
- `cover`: preserve aspect ratio; fill `size` completely; crop overflow.
- `contain`: preserve aspect ratio; fit entirely within `size`.
- `fixed-width`: preserve aspect ratio; width = `size.x`, height derived.
- `fixed-height`: preserve aspect ratio; height = `size.y`, width derived.

### 3.6 Object management (scene graph)

Objects have transform (position/orientation/scale) and may reference a geometry.

Predefined:

- `object` **`$global`** exists at origin and has `$global` geometry attached.
  - `$global` is the **scene graph root** and **cannot be reparented**.
- `object` **`$camera`** exists always, cannot be destroyed, and defines the viewer camera transform.
  - Apart from that, `$camera` is a regular object, can be reparented and have geometry attached

All predefined objects start at `(0 0 0)` with identity rotation and scale.

Parenting / Scene Graph:

- Unless otherwise specified, newly created objects are children of **`$global`**.
- The effective visual transform of an object is computed by application of the objects local transform and its parents effective transform.
  - This implies that transforming the parent will also transform all of its children.

### 3.6.1 Object commands

Lifecycle and hierarchy:

- **S→C** `create-object <obj:[]object> [<g:geom>]`
  - `obj` cannot be `$global` or `$camera`.
  - Duplicate create targets are invalid and ignored.
  - Newly created objects default local transform: pos `(0 0 0)`, rot `(0 0 0)`, scale `(1 1 1)`.
- **S→C** `destroy-object <obj:[]object>`
  - `obj` cannot be `$global` or `$camera`.
  - If the object has child objects in the scene graph, they will be reparented to `$global` preserving world transform (equivalent to `reparent-object $global <child> world`).
- **S→C** `reparent-object <parent:object> <child:[]object> [<transform:reparent-mode>]`
  - `transform` is `world` (default) or `local`.
    - `world` keeps the world transformation of the object as-is
      - This implies the local coordinates of the object will change, but will not visually move.
    - `local` keeps the object’s local transformation as-is:
      - This means the object will potentially move visibly.
  - `child` cannot be `$global`.
  - Loops must not be formed.
    - `parent` must not be `child` or any of it's children.

Geometry attachment:

- **S→C** `set-object-geometry <obj:[]object> [<g:geom>]`
  - Exactly one geometry is attached per object.
  - If `g` is absent, the object becomes invisible.
  - Objects require visible rendered geometry to be interactable (tap/tell/href).

Properties (typed):

- **S→C** `set-object-property <obj:[]object> <property:string> <value:any>`
  - `clickable: bool` (default: `false`) — gates only `tap-object` emission.
  - `textinput: bool` (default: `false`) — gates only `tell-object` emission.
  - `href: [string]` (default: **absent**) — optional; empty/unset removes href.
    - `href` must be an absolute URI string (no relative).

Object properties do not inherit to children.

Multi-action UX:

- Viewer should present available interactions as a selection.
- If exactly one interaction is available, viewer may perform it directly without selection UI.

Transforms (with optional transition):

- **S→C** `set-object-transform <obj:[]object> [<pos:vec3>] [<rot:euler>] [<scale:vec3>] [<t:float>]`
  - Sets the local object transformation relative to its parent.
  - `duration = (t if provided else 0.0)`.
  - `t=0` is truly instant; no single-frame smoothing.
  - `t` must be ≥ 0.

Transition semantics:

- Purpose: **best-effort visual smoothing**, not simulation.
- Time base: viewer monotonic clock; no server timestamps.
- Channels are independent (pos/rot/scale).
- Updating a channel always cancels previous transition on that channel.
- Omitted channel remains unchanged and continues its prior transition if any.
- Guarantee: at the end of duration `t`, the object will be at the target transform.
- During transition, motion is “close enough” for visual purposes; small drift due to jitter is acceptable.
- Drift is bounded by the **longest active transition duration** (bounded, not cumulative).
- `rot:euler` always applies to authored local rotation (`R_local`), independent of tracking rotation layer.

Rotation semantics:

- `rot:euler` is an authoring-friendly Euler representation intended to match the
  "Pan/Tilt/Roll" camera model used by Acknex-style editors.
- Interpolation is performed in quaternion space derived from Euler angles.

### 3.6.2 `rot:euler` interpretation (Pan/Tilt/Roll)

`rot:euler` is a `vec3` interpreted as:

`(pan, tilt, roll)` in **degrees**.

These are **intrinsic** rotations (about the object’s current local axes), applied in this order:

1) **Roll** (first)
2) **Tilt**
3) **Pan** (last)

Axes and sign are defined by *effect* (to avoid ambiguity around "clockwise" views):

- **Pan**: rotate about the **local Up axis**.
  - Positive pan turns the object/camera **to the right**.
  - Rotating around a tiny angle +ϵ, forward is roughly (+ϵ,0,−1).

- **Tilt**: rotate about the **local Left axis** (i.e., -Right).
  - Positive tilt looks **up**.
  - Rotating around a tiny angle +ϵ, forward is roughly (0,+ϵ,−1).

- **Roll**: rotate about the **local Forward axis**.
  - Positive roll tilts the "head" **to the right**.
  - Rotating around a tiny angle +ϵ, up is roughly (+ϵ,1,0).

Notes:

- This convention intentionally matches common "camera feel" controls, and may not match
  the default mathematical sign you would get from blindly applying the right-hand rule.
  Implementations MUST follow the above effect-based definitions.
- Euler angles have gimbal-lock singularities (notably at tilt ≈ ±90°). This does not prevent
  correct internal representation, because implementations are expected to convert Euler to a
  quaternion and operate in quaternion space for interpolation and rendering.

### 3.6.3 Quaternion interpolation guidance

For transitions (`t` provided), the receiver should:

- Convert source and target Euler rotations into quaternions using the above convention.
- Interpolate using a shortest-path spherical interpolation (SLERP) or an equivalent method.
- Apply the interpolated quaternion to produce the rendered orientation during the transition.

### 3.6.4 Tracking (billboard replacement)

Tracking replaces billboard modes. It applies a rotation layer that can aim objects at a target.

- **S→C** `track-object <obj:[]object> [<target:object>] [<mode:track-mode>] [<t:float>]`
  - `obj` cannot be `$global`.
  - `mode` controls how `obj` will move (default: `plane`).
  - t is the transition duration (seconds) for blending between untracked rotation and the tracked rotation (default: `0`).
    - It controls smooth enable/disable (and configuration changes) only; it is not dependent on whether the target moves.
    - `t=0` applies the new tracking state immediately.
  - If `target` omitted: disables tracking (tracking rotation becomes identity, with transition if `t>0`).
  - If target missing at evaluation time: tracking is a no-op until it exists again.
  - If `target` equals `obj`: application ignored (no self-tracking).
  - If `target` is a descendant of `obj`: application ignored (`obj` can never rotate to `target` when `target` always rotates the same amount as `obj`).
  - `$camera` is allowed as `obj` and can track other objects.

Transform chain:

- `T_world(obj) = parent ∘ pos ∘ R_track ∘ R_local ∘ scale`

Tracking computation (in parent space, using local axes):

- `plane`: rotate about local up axis so forward points toward projection of vector to target on plane orthogonal to local up.
- `focus`: rotate local forward to point directly at target while trying to retain local up.

### 3.7 Views and camera control

HackVR does not expose named views. The server moves the viewer’s camera via the `$camera` object.

- Server sets the camera pose with `set-object-transform $camera ...`.
- `$camera` may have geometry attached (HUD-like geometry).

Free-look control:

- **S→C** `enable-free-look <enabled:bool>`
  - When enabled, the viewer may allow immediate local pan/tilt rotation ("free look").
  - Viewers MAY also allow local roll control, but are not required to.
  - When disabled, the viewer should not allow free-look rotation and resets `R_free = identity`.

At connection start, free-look is disabled.

Camera orientation composition:

- Rendered camera rotation `R_render = R_track($camera) ∘ R_local($camera) ∘ R_free`.
- Disabling free-look resets `R_free = identity`.
- Changing `$camera` transform does not disable free-look; free-look remains an additive local offset when enabled.

Background:

- **S→C** `set-background-color <color:color>`
  - Sets the viewer background color for the world.
  - Default background color is `#000080`.

### 3.8 Selectors and globbing

HackVR supports selector syntax for **batching** and **semantic matching**.

Selectors are supported for:

- `object`, `geom`, and `tag` parameters (marked as `[]` in command signatures)

Selectors are **not** supported for:

- `userid`, `intent`

General operation:

- A selector expands to **zero or more concrete values**.
- If a selector expands to zero values, the command becomes a no-op.
- **No deterministic expansion order is required**; commands must not depend on selector expansion order.
- After selector expansion, the command is evaluated as if each expanded concrete command were issued individually. A command error for one expanded instance must not affect other expanded instances.

Multiple selector parameters:

- If a command contains multiple selector parameters, each selector is expanded independently and the command is applied to the **cartesian product** of expansions.

Creation + selectors:

- For commands that *create* entities, selectors are allowed **only as expansions**, not as wildcards.
  - Allowed: `{a,b,c}`, `{0..10}`, `{00..10}`
  - Not allowed in create commands: `*` or `?`

Selector-friendly naming:

- IDs and tags are **dash-grouped identifiers** separated by `-`, e.g. `cheese-01-fancypants`.
- `_` is part of a part; `-` is the part delimiter.
- Reserved IDs start with `$` and are spec-defined.

Globbing syntax:

- `*` matches zero or more parts
  - `cheese-*-done` matches `cheese-done`, `cheese-01-done`, `cheese-01-a-done`, ...
  - `foo-*` matches `foo` as well.
- `?` matches exactly one part
  - `cheese-?-done` matches `cheese-01-done` but not `cheese-done`
- `{a,b,c}` expands to variants
- `{0..10}` expands to `0..10`
- `{00..10}` expands to `00..10` (zero-padded width inferred from endpoints)

Reserved IDs in selectors:

- Globbing includes reserved `$...` IDs unless excluded.
- Reserved IDs that contain `-` split into parts as normal for matching.

Bare `*` fast-path:

- A selector parameter exactly `*` must expand fully (no truncation).

## 4) Types

### 4.1 Primitive types

- **string**: UTF-8 text. Must be non-empty.
- **zstring**: UTF-8 text. May be empty.
- **float**: decimal floating point, matches the regex `^-?\d+(\.\d+)?$`
  - Human-friendly, small-number format:
    - no leading `+`
    - no scientific notation
    - no `.5`.
  - NaN and Inf make no sense in this protocol
  - Precision is viewer-defined and overflow shall be handled gracefully
    - Not every viewer may use IEEE-745 floating points
- **bool**: `true` or `false`
- **vec2**: `(<x:float> <y:float>)` with optional ASCII spaces after `(` and before `)`, and 1+ ASCII spaces between components.
- **vec3**: `(<x:float> <y:float> <z:float>)` with optional ASCII spaces after `(` and before `)`, and 1+ ASCII spaces between components.
- **color**: `#RRGGBB` (24-bit)
  - Can use upper- or lowercase hex characters
- **bytes[N]**: fixed-length hex-encoded bytes of length N (2N hex chars). Accepts upper/lower hex on wire; when used in text contexts, canonicalize to lowercase.
- **any**: a single parameter token whose interpretation is determined by context (e.g., property tables). Validity depends on expected type; `any` does not mean “accept any bytes”. Spaces are allowed per framing; only forbidden control characters apply (except LF allowed generally).
- **uri**: an **absolute URI** as defined in RFC 3986. When displayed to user, may be converted to IRI per RFC 3987 §3.2 guidance. Relative URIs are not allowed. LF and other invalid URI characters are forbidden.

### 4.2 Optional parameter mapping

For an optional parameter `[<x:type>]`:

- If the parameter is **omitted**, it maps to **absent/null**.
- If the parameter is **present but empty**:
  - For `zstring`, it maps to the **empty string** `""`.
  - For all other types, it maps to **absent/null**.

This mapping also applies to optional property types `[T]`.

### 4.3 Identifier types

- **userid**: A user name.
  - Must not contain LF.
  - Must not have leading or trailing Unicode **White_Space** property characters.
  - Must be <128 Unicode codepoints (max 127).
- **object**: Identifier of an *object*. Matches either one of the reserved values (starting with `$`) or the regular expression `^[A-Za-z0-9_]+(-[A-Za-z0-9_]+)*$`.
- **geom**: Identifier of a *geometry*. Uses the same format as the `object` type.
- **intent**: Identifier of an *intent*. Uses the same format as the `object` type.
- **tag**: A semantic name for a part of a *geometry*. Uses the same format as the `object` type.

Reserved identifiers:

- Any identifier starting with `$` is reserved and only spec-defined values are valid.
- Unless explicitly stated, selectors include reserved identifiers.

### 4.4 Structured/enumeration types

- **tapkind**: one of `{primary|secondary}`.
- **sizemode**: one of `{stretch|cover|contain|fixed-width|fixed-height}`.
- **version**: `v` followed by a positive integer, matching `/v[1-9][0-9]*/`.
- **track-mode**: one of `{plane|focus}`.
- **reparent-mode**: one of `{world|local}`.
- **anchor**: one of `{top|center|bottom}-{left|center|right}`.
- **euler**: a `vec3` interpreted as `(pan, tilt, roll)` in **degrees**.
  - Convention: intrinsic rotations, applied **roll → tilt → pan**.
  - Axes/sign:
    - pan: about local Up; positive turns right
    - tilt: about local Left; positive looks up
    - roll: about local Forward; positive tilts head right
  - See **3.6.2 Rotation semantics** for full definition.

### 4.5 Session token type

- **session-token**: base64url without padding (`=` forbidden), characters `[A-Za-z0-9_-]`.
  - Decodes to exactly 32 bytes.
  - Encoded length is exactly 43 chars.
  - Comparison is by decoded bytes.

## 5) Error handling model (non-normative guidance)

HackVR is failure-permissive after establishment:

- Unknown/invalid commands: ignore.
- Missing IDs (unknown object/geom/intent): ignore.
- Missing assets or hash mismatch: show error placeholder and continue.
- Network interruption: the viewer must continue showing the last scene and inform the user (see **2.1.3**).

Strictness scope:

- Establishment handshakes (raw hello and HTTP upgrade) are strict and may close on mismatch.
- After establishment, revert to optimistic model: invalid commands ignored.

Rationale:

- Matches the intended social/exploration “fun and leisure” use cases.
- Avoids leaking information via detailed error messages.

## 6) Assets

Asset semantics:

- Hash is over downloaded bytes.
- Treat `(uri, sha256)` as distinct assets; same uri with different hash is different asset.
- Viewer may cache by `(uri, hash)` or by hash only.
- Hash mismatch or download failure shows placeholder and continues; retry strategy is viewer-defined but should avoid DoS.

### 6.1) Font Assets

- The placeholder for font assets must be a font capable of rendering at least ASCII text.
- A viewer shall at least support the following font formats:
  - TTF

### 6.2) Image Assets

- The placeholder for image assets should be either
  - a flat magenta colored sprite (`#FF00FF`)
  - an easily recognizable pattern like a magenta/white checkerboard pattern
- A viewer shall at least support the following image formats:
  - PNG
  - JPEG

## 7) Implementation limits (anti-DoS guidance)

Clients should enforce reasonable soft limits (reference values):

- Triangle count per geometry: **100,000 triangles**
- Object count: **10,000 objects**
- Object nesting depth: **16 levels**
- Command rate: **1,000 commands/sec**
- Selector expansion
  - for creation commands: A maximum of **1,000 concrete command applications** maximum after any multi-selector expansion
  - for modification/destroy commands: Any number of command applications are allowed, as the number of commands is already bound by other constraints.

Specialized clients may tune these values.

## 8) Miscellaneous guidance and FAQs

- **Cancellable request-input:** viewers can implement cancel as an ad-hoc intent (e.g., “Cancel”).
- **Invisible trigger regions:** model via server-side logic and intents; users only interact with visible geometry.
- **Untagged triangles:** intentionally not removable; tag anything you might want to delete later.
- **Navigation handling:** unknown schemes in `href` are delegated to OS default handler; HackVR schemes navigate to worlds. Navigation behavior (replace/new tab/window) is viewer-defined.

## 9) Open topics to define properly

### Assets, security, and navigation

- Transport profiles for assets (exact allowed schemes per world source).
- Caching strategy (minimal caching/identity semantics are defined, but policies remain open).

### Interaction UX

- Viewer presentation guidelines for intents (menus, keybinds, ordering).
- Rate limiting recommendations for `set-banner` and other UI-affecting commands.
- Interaction selection UI guidelines.
