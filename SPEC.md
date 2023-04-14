# HackVR Protocol

A protocol to connect to basic interactive 3D environments.

## Goal 

The goal of HackVR is to allow a user to connect to a 3D site in the internet. This sites
can contain interactive and hyperlinked 3D spaces the user can explore.

These spaces can be games, virtual museums, interactive applications or any other application.

## Highlevel View

The protocol is designed as an extension to the HTTP protocol similar to how WebSockets are an extension.

HackVR is a stream based protocol that has a line-oriented syntax. Each line contains a command that is
transferred to either the client (HackVR viewer) or the server (HackVR host).

The protocol uses the url scheme `hackvr`, which follows the same rules as the `http` scheme. Similar to
`https`, there's also the `hackvrs` scheme that uses a TLS encrypted communication.

## Structural Decisions

### Coordinate System

HackVR uses the right-handed OpenGL coordinate system. In a standard-oriented view, the camera has the following coordinates:

| Direction | Vector     |
| --------- | ---------- |
| Right     | (1, 0, 0)  |
| Upward    | (0, 1, 0)  |
| Forward   | (0, 0, -1) |

## Protocol

HackVR is medium independent and only requires a bi-directional data stream.

This stream is then chopped into `CR` `LF` terminated lines.

Each line contains a single command and its parameters. Valid characters in a line are all legal UTF-8 characters, excluding the ASCII control codes. The only allowed control codes in a line are `TAB` and `LF`.

A lone `LF` signals a line break inside an argument, so a command can receive multiline text as an argument. `TAB` is used to separate arguments. This means that an argument is not allowed to contain a `TAB` character, or any other control code, except `LF`.

The number of arguments varys between the commands.


### HTTP Upgrade Protocol

This version of the protocol is based on HTTP and allows integrating HackVR into already existing infrastructure:

The initial handshake is performed by a HTTP 1.1 connection upgrade:

```
GET /example HTTP/1.1
Host: www.example.com
Connection: upgrade
Upgrade: hackvr
```

After that, the command protocol is used. Additional HTTP headers are allowed, but ignored.

## Commands

The command documentation uses a syntax that is common to regular command line applications:
- A single word is considered verbatim (`echo`)
- Anything in square brackets is considered an optional element (`[optional]`)
- Anything in pointy brackets is considered a variable argument (`<x>`)
- Anything in curly brackets can be repeated several times, including zero (`{ <x> <y> }`)

Arguments can also be optional, these will be noted as `[<var>]`.

Types are for variable arguments are separated by a `:` from the name: `<name:type>`

`type` can be one of the following:

| Type     | Syntax                            | Description                                                       | Examples                   |
| -------- | --------------------------------- | ----------------------------------------------------------------- | -------------------------- |
| string   |                                   | Any text is allowed.                                              | `Hello`, `This is "mice"`  |
| float    | `-?\d+.?\d*`                      | Contains a decimal floating point number.                         | `3.14`, `0`, `-1.2`        |
| bool     | `true\|false`                     |                                                                   | `true`, `false`            |
| vec2     | `(<x:float> <y:float>)`           | A position in 2D space.                                           | `(1.0 2.0)` `(0 0)`        |
| vec3     | `(<x:float> <y:float> <z:float>)` | A position in 3D space.                                           | `(1.0 2.0 3.0)`, `(0 0 0)` |
| color    | `#RRGGBB`                         | A 24 bit sRGB color                                               | `#FF0000`, `#FFFFFF`       |
| userid   | `[A-Za-z0-9\-\_]+`                | A user name                                                       | `xq`, `anonymouse`         |
| object   | `\$?[A-Za-z0-9\-\_]+`             | A unique identifier for an object.                                | `$global`, `player_1`      |
| view     | `\$?[A-Za-z0-9\-\_]+`             | A unique identifier for a view.                                   | `$global`, `nice-view`     |
| geom     | `\$?[A-Za-z0-9\-\_]+`             | A unique identifier for a geometry.                               | `$global`, `human-head`    |
| bytes[N] | `[A-Za-z0-9]{2*N}`                | A hexadecimal sequence of hex-encoded bytes. N is a fixed length. | `00`, `1337`, `BADECAFE`   |

#### Chat System

> `chat <user:userid> <message:string>`

Notifies that a chat message by `<user>` was sent. `<message>` contains the sent text. If the command is sent from a client, the user name
may be empty. Chat messages from a server always have a user name present.

Chat messages from a client will be echoed by the server back to client. Note that chat messages might be silently ignored by the server
when the user is muted, not authenticated or due to similar reasons.

#### Authentication (optional)

> `set-user <user:userid>` (client command)

Attempts to change the active user account to `<user>`. If authentication is required, the following command is issued:

> `request-authentication <user:userid> <salt:string>` (server command)

Requests authentication for the `<user>`. The password is to be hashed with hex-encoded 16 byte `<salt>`. The client is then to respond
with the following command:

> `authenticate <user:userid> <pwhash:bytes[?]>` (client command)

The `<pwhash>` is a Argon2 hash of the users password hashed with the `<salt>` that was provided by `request-authentication`. This allows
the server to hash each users password with a different salt to decrease authentication vulnerabilities.

After this, one of the two following commands is issued:

> `accept-user <user:userid> [<session-token:string>]` (server command)
> 
> `reject-user <user:userid> <reason:string>` (server command)

If authentication fails, either after `set-user` or `authenticate`, the server responds with `reject-user` and gives a human-readable message in `<reason>`.

Otherwise, the user is successfully authenticated when the client receives `accept-user`. This command also optionally can provide a `<session-token>` the user can use to resume a session later on without authenticating itself again. This is done by issuing the following command:

> `resume-session <user:userid> <session-token:string>` (client command)

This command is then responded with either `accept-user` or with `reject-user` and a reason. If `accept-user` is sent, the session token may be refreshed by the server. If no session token is provided, the token is still valid and can be used again later.

#### Geometry Management

Geometries are triangle soups that can be attached to objects. Triangles can be added and removed from geometries, but there are no queries possible. This means the server has to keep track of geometries modified at runtime, but can just fire-and-forget most geometry creation.

There is a single predefined geometry called `$global`. This geometry is assigned to the object `$global` by default and can be used to construct a global scene without having to create boilerplate objects and geometries first.

> `create-geometry <id:geom>` (server command)

> `destroy-geometry <id:geom>` (server command)

> `add-triangle-list <id:geom> { <p0:vec3> <p1:vec3> <p2:vec3> <color:color> }` (server command)
>
> `add-triangle-strip <id:geom> <color:color> <p0:vec3> <p1:vec3> <p2:vec3> { <pos:vec3> }` (server command)
> 
> `add-triangle-fan <id:geom> <color:color> <p0:vec3> <p1:vec3> <p2:vec3> { <pos:vec3> }` (server command)

Adds new triangles to `<id>`. `add-triangle-list` will add as many triangles as given, each triangle being of a unique color.

`add-triangle-strip` and `add-triangle-fan` will add at least a single triangle, but both allow
to add more triangles that share vertices with previous tris. All triangles added with
those commands share the same color.

In `add-triangle-strip`, each additional point will create a new triangle from the new point and the last two recent points added. This way, a long chain of triangles can be formed.

In `add-triangle-fan`, each additional point will create a new triangle from the frist and the last point added. This way, all new added triangles will fan around a single center point.

#### Object Management

Objects are things in the 3D space that have a position, orientation and scale. Objects can have a geometry attached, which makes them visible.

There is a predefined object `$global` that is present without creation. It has the geometry `$global` attached, which allows the creation of 3D scenes without boilerplate. This object is located at (0,0,0) with no rotation or scale.

> `create-object <obj:object> [<g:geom>]` (server command)

> `destroy-object <obj:object>` (server command)

> `add-child <parent:object> <child:object> [<transform>]` (server command)

Makes `<child>` a child of `<parent>`. This means that all coordinates of `<child>` are now relative to the coordinate system of `<parent>`.

`<transform>` can have several values:

| Transform         | Description                                                                           |
| ----------------- | ------------------------------------------------------------------------------------- |
| `world` (default) | Keeps the current world space transformation, so the object does not visually change. |
| `local`           | Keeps the local transformation and just reparents the object.                         |

> `set-object-geometry <obj:object> <g:geom>` (server command)

> `set-object-property <obj:object> <property:string> <value:any>` (server command)

Valid properties are:

| Property    | Type | Description                                                                                                                                                                                                              |
| ----------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `href`      | URI  | Sets a hyperref to the given object. If the user clicks the object, the hyperref is resolved and opened. If a HackVR document is opened, the viewer should close the current connection and connect to the new document. |
| `clickable` | BOOL | If `true`, when the user clicks the object, a `tap-object` command should be sent.                                                                                                                                       |
| `textinput` | BOOL | If `true`, the user can send a text message to an object. This will result in a `tell-object` command.                                                                                                                   |

#### View Management

> `create-view <view-id> <pos:vec3> <view-dir:vec3>` (server command)

> `destroy-view <view-id>` (server command)

#### Interaction

> `enable-movement <enabled:bool>` (server command)

Enables or disables autonomous user movement. The movement is usually a fly-through camera.

> `set-view <id:view> [<smooth:bool>] [<duration:float>]`

Moves the camera view to `<view-id>`. If `<smooth>` is present and `true`, the camera will perform a smooth camera transition from the current position to the new one.

The transition takes `<duration>` seconds or, if `<duration>` is not present, roughly 500 ms.

> `tap-object <id:object> <button> <triangle-index:uint>` (client command)

Taps an object with the `primary` or `secondary` mouse `<button>`. This is an interaction when a user clicks on an object with the mouse.

`<triangle-index:uint>` contains the triangle the user clicked.

> `tell-object <id:object> <text:string>` (client command)

Sends a text message to an object. 

> `change-view <pos:vec3> <view-dir:vec3>` (client commmand)

The user moved the camera to another location