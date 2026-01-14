# HackVR Protocol Draft — Consolidated Edit Actions (from full discussion)

> This file lists required semantic edit actions by spec section/heading.
> It is intended to be applied incrementally to the HackVR protocol draft to build a clean git history.
> Language/style/layout refinements are out of scope; this is purely semantic + correctness edits.

---

## 1) Intent and philosophy

- Add/clarify that **strict failure rules only apply during connection establishment handshakes** (raw `hackvr-hello` phase and HTTP Upgrade phase). After establishment, the protocol uses optimistic error handling (unknown/invalid commands ignored).
- Keep the core philosophy unchanged (server-authoritative, optimistic, discrete interaction), but ensure later edits (sessions/tracking) do not reintroduce hidden client-side state assumptions.

---

## 1.2 Coordinate system

- No required semantic changes from the discussion.

---

## 2) Transport, framing, and default upgrade paths

### 2.1 Byte stream + line protocol

- Keep CRLF-terminated, TAB-separated UTF-8 line protocol.
- Add explicit: **lines with invalid UTF-8, stray CR, or other framing violations shall be ignored as command errors** (post-establishment).
- Add a recommended **optimistic line length limit ~1024 bytes including CRLF**:
  - If exceeded, treat as command error (ignored).
  - Keep this as guidance unless you want it normative; ensure it is compatible with geometry streaming (servers must emit multiple lines).

### 2.1.3 End-of-stream behavior

- Replace/adjust prior reconnect guidance:
  - Viewer **MUST NOT automatically reconnect** in any case.
  - Any (re)connection attempt must be an explicit **user action**.
  - Viewer still must keep showing last scene and inform user connection closed.

### 2.2 URL schemes

- Update/expand schemes and transport profiles (these are normative mappings, not just names):
  - `hackvr://` = raw TCP, unencrypted; HackVR line protocol starts immediately after establishment handshake (see `hackvr-hello`).
  - `hackvrs://` = raw TCP + TLS 1.2/1.3 **or later**; HackVR starts after TLS + `hackvr-hello`.
  - `http+hackvr://` = HTTP/1.1 Upgrade over HTTP.
  - `https+hackvr://` = HTTP/1.1 Upgrade over HTTPS.

### 2.3 Default network path: HTTP/1.1 Upgrade

- Specify required HTTP Upgrade success criteria:
  - Server must reply with **101 Switching Protocols**.
  - Response must include headers: `Connection: upgrade` and `Upgrade: hackvr` (header names case-insensitive).
  - HackVR command stream begins **immediately after HTTP headers** (after the blank line).
- Specify failure handling:
  - Viewer must display failure to the user.
  - If server returns **2xx**, viewer should display the **plaintext response body** (helpful for debugging).
- Add version signaling for HTTP establishment:
  - Protocol version is carried via HTTP header `HackVr-Version: v1` (must be `v1` for current spec).
  - Version negotiation is conceptually handshake-abstract (see Version section below), but HTTP currently pins to v1.
- Redirect binding rule:
  - Session/origin binding for HTTP profile uses **the request that finally opens the HackVR connection** (the final request that successfully upgraded).

---

## 3) Commands — global conventions

- Update optional parameter mapping examples only where needed:
  - Keep semantics: omitted optional param => null/absent; present-but-empty => empty only for `zstring`, otherwise null/absent.
- Add global rule: **type validation may be stricter than framing**:
  - Framing permits LF in parameters generally, but types (e.g., `userid`, `uri`) may forbid LF.
  - Type violations are command errors (ignored post-handshake).
- Add/clarify: after establishment, unknown/invalid commands are ignored (optimistic model), not connection-fatal.

---

## 3.1 Chat

- Split into two commands (direction-specific) to avoid ambiguous optional user field:
  - **S→C** `chat <user:userid> <message:string>` (server must always include user).
  - **C→S** `chat <message:string>` (viewer omits user field; server ignores any user field if present).
- Enforce `message` must be `string` (non-empty). Empty chat messages are nonsensical and should be omitted rather than sent.

---

## 3.2 Authentication and sessions

### 3.2.x Authentication (Ed25519)

- Keep Ed25519 challenge/response model, but apply these fixes:
  - `nonce:bytes[16]` may be upper/lower hex on wire; receivers accept both.
  - When used in signing strings, the nonce must be **canonical lowercase hex**.
  - `authenticate` signing input uses canonical lowercase hex nonce.
  - No string normalization anywhere; viewer signs exactly what it received, after canonical lowercase hex conversion of nonce.
- State-machine closure:
  - After **C→S** `authenticate ...`, server must respond with exactly one of:
    - **S→C** `accept-user ...` (success) or
    - **S→C** `reject-user ...` (failure).
  - After `reject-user`, viewer may restart with `set-user` again.
- `userid` allowed to be rich Unicode (e.g., emoji), but must obey updated `userid` constraints (see Types).

### 3.2.x Sessions — redesign (tokens are NOT auth/bearer)

> Major rewrite: remove prior “bearer token” semantics.

- Remove `session-token` from `accept-user`.
- Remove `userid` from `resume-session`.
- Remove all text that states `set-user` invalidates session tokens or that session tokens are tied to authentication.
- Redefine session tokens as **session identifiers / context hints**, not authentication:
  - Session tokens identify server-side state (think “savegame id”), not identity.
  - Tokens may be shared across viewers.
  - Tokens are **not invalidated by use**; multiple connections may resume the same token if server allows (e.g., lobby/instance).
  - Server must not treat possession of a token as authentication; if access control is needed, server must implement it separately (may require authentication separately).
- Add commands:
  - **S→C** `announce-session <token:session-token>`
    - Sets/refreshes the token associated with the current connection/session context.
    - Rotation/refresh semantics:
      - If token differs from the previously announced token for this **connection context**, the previously announced token becomes invalid (effectively revoked).
      - If token is the same as previously announced: refresh/extend lifetime, does not invalidate share links.
  - **S→C** `revoke-session <token:session-token>`
    - Informs viewer that token is no longer valid/usable (server/world-wide invalidity).
- Add/keep:
  - **C→S** `resume-session <token:session-token>`
    - Semantics are server-defined: may restore state, switch lobbies, be idempotent or not; client should rely on scene updates and `set-banner` for user feedback.
- Establishment-time session token carriage:
  - For raw `hackvr(s)://`: add optional session token parameter to the **client** hello (see `hackvr-hello` below).
  - For HTTP upgrade: add HTTP request header `HackVr-Session: <session-token>`.
  - Establishment token is treated as if the client sent `resume-session <token>` as the **first client action** on the connection.
- World-state baseline rule:
  - Protocol assumes empty/default world state on connection.
  - Session resumption does not assume any client-retained scene; server must recreate scene explicitly if desired.
- Context scope rule:
  - “Connection/session context” means the lifetime of the transport connection (open→close).
  - Rotation/refresh semantics for `announce-session` are defined with respect to the connection context.
  - `resume-session` does not create a new context.
- Token encoding rules (see Types):
  - session tokens are base64url without padding, decode to exactly 32 bytes, encoded length 44 chars, compared by decoded bytes.
- URL fragment as session token (viewer convenience):
  - For HackVR URLs, fragment `#<token>` is interpreted as a session token and injected into the connect-time token parameter/header.
  - Fragment is not transmitted as part of `uri` on wire; it is viewer-side parsing only.

---

## 3.3 Graphical Interface

### 3.3.1 Text Input

- Fix directionality:
  - `cancel-input` is **S→C only**; it cancels the previous `request-input` (idempotent; no-op if none active).
  - `send-input` remains **C→S**; empty text allowed.
- Request replacement semantics:
  - A new `request-input` replaces any previous active request-input.
  - Viewer shall not clear current user draft input when replacing (keeps draft).
- Orthogonality:
  - `request-input` is orthogonal to `request-user` (both may be active; viewer may present both without forced focus popups).
  - Correlation is server-side; there is no protocol correlation id for `request-input` / `send-input`.

### 3.3.2 Banner

- Change signature and semantics:
  - `set-banner <text:[string]> [<t:float>]` (text should be optional string-like)
  - Empty/absent text clears banner (no “empty banner” semantic value).
  - Keep auto-hide behavior when `t` provided.

---

## 3.4 World Interaction

### 3.4.1 Object Interaction

- Enforce:
  - Viewer must not send `tap-object` for hits with empty/unreferenceable tag.
  - Viewer must not send `tap-object` for objects with `clickable=false` (see properties below).
- Keep `tell-object` semantics; empty allowed.

### 3.4.2 Intents

- Clarify “default intents” semantics:
  - These intents are **predefined/initially present** on connect (`$forward`, `$back`, `$left`, `$right`, `$up`, `$down`, `$stop`).
  - They may be destroyed and recreated (not “always exist”).
  - Viewer may display destroyed predefined intents as disabled UI controls for layout consistency (must not emit `intent` for non-existent intents).
- Keep intents as upsert:
  - `create-intent` upserts label, including for predefined intents.
  - Intents are not selector-enabled; `intent` triggers include view-dir.

### 3.4.3 Raycast mode

- Make raycast mode strictly boolean-gated and deterministic:
  - `raycast-request` sets `raycast_mode = true` (idempotent).
  - `raycast-cancel` sets `raycast_mode = false` (idempotent).
  - `raycast` must only be sent when raycast_mode was true; it sets raycast_mode false before emitting.
  - Multiple `raycast-request` do not queue rays; they just keep mode true until one ray or cancel.
- Standardize name: use `raycast-cancel` only; remove any “cancel-raycast” mentions.

---

## 3.5 Geometry management

### 3.5.1 Triangle soups

- Winding/culling/picking:
  - Winding order does not matter; no backface culling. Triangles are visible and pickable from both sides.
- Strip/fan exact construction:
  - Triangle strip: new vertex `pos` forms triangle `(seq[n-2], seq[n-1], pos)`.
  - Triangle fan: new vertex `pos` forms triangle `(seq[0], seq[n-1], pos)`.
- Color semantics:
  - `add-triangle-strip` and `add-triangle-fan` apply **one color per invocation** (single color for all triangles produced).
  - If per-triangle color is needed, server must use `add-triangle-list`.
- Untagged permanence:
  - Keep and emphasize: empty/missing tag is unreferenceable and intentionally non-removable/non-tappable.
  - `remove-triangles` can only remove tagged triangles.
- Selector `*` behavior:
  - For tag selector `*`, it matches all **tagged** triangles; untagged remain permanent.

### 3.5.2 Text geometries

- Rename/retarget to `uri` type for font:
  - `create-text-geometry <id:[]geom> <size:vec2> <font-uri:uri> <font-sha256:bytes[32]> <text:string> [<anchor:anchor>]`
- Remove geometry-level billboard mode parameter entirely (see Tracking section).
- Property updates:
  - `set-text-property <id:[]geom> <property:string> <value:any>`
  - Define typed property table at least:
    - `text: string` (non-empty)
    - `color: color`
  - Empty handling is based on expected type (see `any` rules below).

### 3.5.3 Sprite/image geometries

- Rename/retarget to `uri` type:
  - `create-sprite-geometry <id:[]geom> <size:vec2> <uri:uri> <sha256:bytes[32]> [<size-mode:sizemode>] [<anchor:anchor>]`
- Remove geometry-level billboard mode parameter entirely (see Tracking section).
- Asset caching semantics:
  - Treat (uri, sha256) as distinct assets; same uri with different hash is different asset.
  - Viewer may cache by (uri,hash) or by hash only.
  - Hash mismatch or download failure shows placeholder and continues; retry strategy is viewer-defined but should avoid DoS.
  - Viewer provides fallback default font + image placeholder.

---

## 3.6 Object management (scene graph)

### 3.6.x Predefined objects

- Add predefined object `$camera`:
  - Exists always, cannot be destroyed.
  - Defines the viewer camera transform (replaces `set-view-transform` and `set-view-parent` entirely; remove those commands).
  - May have geometry attached (allows HUD-like geometry).
- Keep `$global` as root:
  - Exists always; cannot be destroyed or reparented.

### 3.6.1 Object lifecycle and hierarchy

- Creation defaults:
  - Newly created objects default local transform: pos `(0 0 0)`, rot `(0 0 0)`, scale `(1 1 1)`.
  - Newly created objects are children of `$global` unless otherwise specified.
- `destroy-object` child handling:
  - When destroying an object, children are reparented to `$global` **preserving world transform** (equivalent to `reparent-object $global <child> world`).
- Duplicate create semantics:
  - Duplicate `create-object` / `create-geometry` targets are invalid and ignored (no recreation/upsert).
  - If a server wants to recreate, it must explicitly destroy first.

### 3.6.1 Geometry attachment

- Keep `set-object-geometry` semantics:
  - If geometry absent, object is invisible.
- Add interaction requirement:
  - Objects require **visible rendered geometry** to be interactable (tap/tell/href).
  - No invisible colliders in protocol.

### 3.6.1 Object properties (typed)

- Change signature:
  - `set-object-property <obj:[]object> <property:string> <value:any>`
- Define typed property table and rules:
  - `clickable: bool` — gates only `tap-object` emission.
  - `textinput: bool` — gates only `tell-object` emission.
  - `href: [string]` — optional; empty/unset removes href.
    - `href` must be absolute URI string (no relative).
    - Viewer must confirm navigation and show full target including scheme.
    - Unknown schemes delegated to OS default handler; HackVR schemes open as worlds.
- Non-inheritance:
  - Object properties do not inherit to children.
- Multi-action UX:
  - Viewer should present available interactions as a selection.
  - If exactly one interaction is available, viewer may perform it directly without selection UI.

### 3.6.1 Transforms and transitions

- Set default duration:
  - `duration = (t if provided else 0.0)`.
  - `t=0` is truly instant; no single-frame smoothing.
- Channel updates:
  - Updating a channel always cancels previous transition on that channel.
  - Omitted channel remains unchanged and continues its prior transition if any.
- Rotation under tracking:
  - `rot:euler` always applies to authored local rotation (`R_local`), independent of tracking rotation layer.

---

## 3.6.2 Rotation semantics (Pan/Tilt/Roll)

- Keep effect-based Euler convention as-is (pan/tilt/roll degrees; roll→tilt→pan intrinsic order).
- Ensure any references to “billboard rotation” are removed (now handled via tracking command).

---

## 3.7 Views and camera control

- Remove `set-view-transform` and `set-view-parent` commands entirely.
- Replace with `$camera` object:
  - Server moves/rotates `$camera` via `set-object-transform $camera ...`.
- Free-look:
  - Keep `enable-free-look <enabled:bool>`.
  - Composition and reset:
    - Rendered camera rotation `R_render = R_track($camera) ∘ R_local($camera) ∘ R_free`.
    - Disabling free-look resets `R_free = identity`.
  - Changing `$camera` transform does not disable free-look; free-look remains an additive local offset when enabled.
- Background remains:
  - `set-background-color` still applies.

---

## 3.8 Selectors and globbing

- Rename conceptual wording:
  - Replace “kebab-case” with “dash-grouped identifiers”.
  - Part delimiter is `-`; `_` is part of a part.
- Ensure regex alignment:
  - User-defined IDs use `[A-Za-z0-9_]` parts only; reserved IDs start with `$` and are spec-defined.
- Globbing semantics:
  - `*` matches zero or more parts; `foo-*` matches `foo` as well.
  - `?` matches exactly one part.
  - `{a,b}` and numeric ranges unchanged.
- Reserved IDs in selectors:
  - Globbing includes reserved `$...` IDs unless excluded.
  - Reserved IDs that contain `-` split into parts as normal for matching.
- Creation with selectors:
  - Creation with selectors is equivalent to executing each expanded command individually.
  - For create targets that already exist: those applications are ignored; other expansions may still succeed.
- Bare `*` fast-path:
  - Special-case selector parameter exactly `*` to always expand fully (no truncation).
  - Update DoS guidance accordingly (general “1000 applications” guidance does not apply to bare `*`).

---

## 4) Types

### 4.1 Primitive types

- Fix float regex typo and define strict float format (no exponents, no `.5`):
  - Accept only `-?\d+(\.\d+)?` (no leading `+`, no scientific notation).
  - Clarify any additional constraints where used (e.g., durations must be ≥ 0).
- Update vec parsing to be whitespace-tolerant:
  - Allow optional ASCII spaces after `(` and before `)`.
  - Require 1+ ASCII spaces between components.
  - Example: `(  1   2  3 )` valid; TAB is not allowed (TAB is command separator).
- Define `any`:
  - `any` is a single parameter token whose interpretation is determined by context (e.g., property tables).
  - Validity depends on expected type; `any` does not mean “accept any bytes”.
  - Spaces are allowed in parameters per framing; only forbidden control characters apply (except LF allowed generally).
- Define new `uri` type:
  - `uri` must be an **absolute URI** as defined in RFC 3986.
  - When displayed to user, may be converted to IRI per RFC 3987 §3.2 guidance.
  - This forbids LF and other invalid URI characters.
  - Relative URIs are not allowed.
- bytes:
  - `bytes[N]` accepts upper/lower hex on wire; interpreted as decoded bytes.
  - When used in text contexts (e.g., signing strings), canonicalize to lowercase hex.

### 4.2 Optional parameter mapping

- Keep mapping, but ensure it is referenced for property optional types:
  - For optional property types `[T]`, present-but-empty maps to null/unset.

### 4.3 Identifier types

- Replace `\w` regex with deterministic ASCII:
  - `object`, `geom`, `intent`, `tag` for user-defined values:
    - `^[A-Za-z0-9_]+(-[A-Za-z0-9_]+)*$`
- Reserved identifiers:
  - Any identifier starting with `$` is reserved and only spec-defined values are valid.
  - Unless explicitly stated, selectors include reserved identifiers.

### 4.3 `userid`

- Update `userid` constraints:
  - Must not contain LF.
  - Must not have leading or trailing Unicode **White_Space** property characters.
  - Must be <128 Unicode codepoints (max 127).
  - Rich Unicode is allowed (including emoji).

### 4.4 Structured/enumerations

- Remove `billboard` enumeration (fixed/y/xy) from types (tracking replaces it).
- Add `track-mode` enumeration:
  - `{plane | focus}` (plane = rotate on local up axis only; focus = look-at target)
- Keep other enums as before.

### Session token type (new)

- Add `session-token` type:
  - Base64url without padding (`=` forbidden), characters `[A-Za-z0-9_-]`.
  - Decodes to exactly 32 bytes.
  - Encoded length is exactly 44 chars.
  - Comparison is by decoded bytes.

---

## 5) Error handling model

- Clarify strict-vs-optimistic scope:
  - Establishment handshakes (raw hello and HTTP upgrade) are strict and may close on mismatch.
  - After establishment, revert to optimistic model: invalid commands ignored.
- Keep general optimistic behavior for missing IDs/assets; show placeholders for assets.

---

## 6) Implementation limits (anti-DoS guidance)

- Keep soft limits (selector expansion, triangles, objects, nesting depth, command rate), but update selector expansion guidance:
  - Bare `*` selector must expand fully; do not truncate based on the “1000 applications” guidance in that case.
- Ensure “1000 applications max per command” is guidance and does not introduce non-deterministic partial behavior requirements; emphasize it is a client soft limit.

---

## 7) Open topics

- Update open topics list to remove billboard geometry mode items (now replaced by tracking), and add/adjust:
  - Tracking command semantics are now defined; remaining open topic is optional future extensions only.
  - Asset scheme allowlists and caching remain open (but now minimal caching/identity semantics are defined).
  - Interaction UX guidelines remain open but now include “interaction selection UI” rule.

---

## NEW: Connection establishment — raw handshake (`hackvr-hello`) section (add under Transport)

> Add a dedicated section that defines raw `hackvr(s)://` establishment.

- Add handshake-only command definitions:
  - **C→S** `hackvr-hello <max-version:version> <uri:uri> [<session-token:session-token>]`
    - `uri` must not contain fragment (fragment is viewer-local session-token extraction).
  - **S→C** `hackvr-hello <max-version:version>`
- Define version negotiation:
  - Versions match `/v[1-9][0-9]*/`; parse integer suffix; effective version is min.
  - Parse failure or unsupported effective version => close; viewer should inform user, server may log.
- Define strictness:
  - Both sides must send hello immediately after connect.
  - First received line must be hello; otherwise close.
  - No other commands allowed pre-hello.
  - After hello exchange, protocol enters optimistic mode.
- Define connect-time session token behavior:
  - Optional `session-token` in client hello is treated as if client sent `resume-session <token>` first.

---

## NEW/UPDATED: Session commands section

- Add/define:
  - **S→C** `announce-session <token:session-token>`
  - **S→C** `revoke-session <token:session-token>`
  - **C→S** `resume-session <token:session-token>` (no userid)
- Define:
  - Tokens are not authentication credentials.
  - Tokens are shareable, reusable, not invalidated by use.
  - Tokens may expire; servers should revoke when feasible.
  - `announce-session` refreshes/rotates token with semantics specified above.
  - URL fragment `#token` sets connect-time token (viewer convenience).
- Define connection-only reasoning:
  - Protocol cannot assume anything outside connection lifetime; scene must be recreated by server.

---

## NEW/UPDATED: Tracking / billboard replacement section

- Remove billboard mode parameters from geometry creation.
- Add `track-object` command:
  - **S→C** `track-object <obj:[]object> [<target:object>] [<mode:track-mode>] [<t:float>]`
  - `t` defaults to 0.0, cancels prior tracking transition.
  - If target omitted: disables tracking (tracking rotation becomes identity, with transition if t>0).
  - If target missing at evaluation time: tracking is no-op until it exists again.
  - If obj is `$global`: command application ignored.
  - If target equals obj: target ignored / application ignored (no self-tracking).
  - `$camera` is allowed as obj and can track other objects.
- Define transform chain:
  - `T_world(obj) = parent ∘ pos ∘ R_track ∘ R_local ∘ scale`
- Define tracking computation in parent space using local axes:
  - `plane`: rotate about local up axis so forward points toward projection of vector to target on plane orthogonal to local up.
  - `focus`: rotate local forward to point directly at target (with deterministic up-hint rules).
- Define camera free-look composition with tracking:
  - `R_render = R_track ∘ R_local ∘ R_free`
  - disable free-look resets `R_free`.

---

## Miscellaneous corrections and FAQs to add

- Add FAQ: cancellable `request-input` can be implemented by creating an ad-hoc intent (e.g., “Cancel”).
- Add FAQ: “invisible trigger regions” can be modeled via server-side logic and intents; user only interacts with visible geometry.
- Add guidance: untagged triangles are intentionally not removable; tag anything you might want to delete later.
- Add guidance: unknown schemes in `href` are delegated to OS default handler; HackVR schemes navigate to worlds; navigation is viewer-defined (replace/new tab/window).
- Add explicit: session tokens are same-origin bound using handshake-derived (domain,port,path,query) for raw, and Host+request-target for HTTP; fragment ignored.

