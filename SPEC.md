# HackVR Specification

**Note:**
This specification is inofficial and based on the development of HackVR Turbo (which is based on the original hackvr)

## Virtual Environment

The HackVR virtual environment is structured in a tree of groups. Each group contains a set of polygons with 1 … n vertices. Each polygon may have it's own color, chosen from a palette. This environment is built and modified via commands on `stdin`. Interactions by the user with the environment are passed to `stdout`.

### Groups
Groups are unordered sets of polygons with a transformation in 3D space. Each vertex of the polygons is relative to the group origin. Transformations on the group (or any of its parents) will thus indirectly apply to the vertices.

### Polygons (Shapes)
Each polygon may have 1 (circle) up to n (n-gon) vertices. Each polygon is allowed to have any orientation in space, but is required to have all vertices to be on a plane. HackVR is allowed to enforce this and normalize all polygons to be on their mean plane.
A polygon also has a velocity relative to its group and a color, chosen from a palette.

### Colors (Palette)
HackVR has a default palette with 16 different colors:

| Color Index | Visual Description / Name | Default Value |
|-------------|---------------------------|---------------|
| 0           | Black                     | #111111       |
| 1           | White                     | #EEEEEE       |

### Coordinate System

HackVR uses the right-handed OpenGL coordinate system. In a standard-oriented view, the camera has the following coordinates:

| Direction | Vector     |
|-----------|------------|
| Right     | (1, 0, 0)  |
| Upward    | (0, 1, 0)  |
| Forward   | (0, 0, -1) |

## I/O
HackVR communicates via `stdin`/`stdout`. Commands are passed on a line-by-line basis, each line is terminated by a LF character, optionally preceeded by a CR character.
Each line must be encoded in valid UTF-8.

## Commands

Commands in a line are separated by one or more whitespace characters (SPACE, TAB). Commands are usually prefixed by a group selector `[group]`, only exception to that are `version` and `help`. 

Everything after a `#` in a line is considered a comment and will be ignored by the command processor. The same is true for lines not containing any non-space characters.

> TODO: group names can be globbed in some cases to operate on multiple groups
>  some commands that take numbers as arguments can be made to behave relative by putting + before the number. makes negative relative a bit odd like:
> ``` 
> user move +-2 +-2 0
> groupnam* command arguments
> ```

## Input Commands

### `help`

### `version`

### `[groupspec] deleteallexcept grou*`
Deletes all groups not matching `grou*`.

### `[groupspec] deletegroup grou*`
Deletes all groups matching `grou*`.

### `[groupspec] assimilate grou*`

### `[groupspec] renamegroup group`
Renames and merges groups. Selects all groups with `groupspec` and renames them to `group`. When multiple groups are selected, those groups are merged into the master group.

> TODO: Define how transforms will merge

### `[groupspec] status`
**deprecated**

Just outputs a variable that is supposed to be loops per second.`

### `[groupspec] dump`
Tries to let you output the various things that can be set.`

### `[groupspec] quit`
Closes hackvr only if the id that is doing it is the same as yours.`

### `[groupspec] set`

### `[groupspec] physics`

### `[groupspec] control grou*`
> Globbing this group could have fun effects

### `[groupspec] addshape color N x1 y1 z1 ... xN yN zN`

### `[groupspec] export grou*`

### `[groupspec] ping any-string-without-spaces`

d
### `[groupspec] rotate [+]x [+]y [+]z`

### `[groupspec] periodic`
Flushes out locally-cached movement and rotation

### `[groupspec] flatten`
Applies the current group transform to all contained vertices in the selected groups and will reset set the group transforms to *none*.

### `[groupspec] move [+]x [+]y [+]z`

### `[groupspec] move forward|backward|up|down|left|right`

## Output Commands

### `name action targetgroup`

when a group is clicked on using the name set from the command line. usually `$USER`



## Changes

- Encoding is assumed UTF-8
- Max. line length excluding the `\n` is 1024 bytes
- Polygons are required to be *flat*

## TODO

- Define relative coordinate system for "forward/backward/…"
- Full color table
- Imlement `subsume` command

### Questions
- Shape velocity
- Transformation order/execution
- Colors