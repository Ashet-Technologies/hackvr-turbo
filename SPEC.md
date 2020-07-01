# HackVR Specification

**Note:**
This specification is inofficial and based on the development of HackVR Turbo (which is based on the original hackvr)

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

### `[groupspec] deletegroup grou*`

### `[groupspec] assimilate grou*`

### `[groupspec] renamegroup group`

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

### `[groupspec] scale x y z`

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

## TODO

- Define coordinate system
- Define relative coordinate system for "forward/backward/…"