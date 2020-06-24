# HackVR Specification

**Note:**
This specification is inofficial and based on the development of HackVR Turbo (which is based on the original hackvr)


hackvr help output:

# commands that don't get prepended with groupname: help, version
# command format:
# group names can be globbed in some cases to operate on multiple groups
# some commands that take numbers as arguments can be made to behave relative
# by putting + before the number. makes negative relative a bit odd like:
#   user move +-2 +-2 0
# groupnam* command arguments
# commands:
#   deleteallexcept grou*
# _ deletegroup grou*
#   assimilate grou*
#   renamegroup group
#   status  # old. just outputs a variable that is supposed to be loops per second.
#   dump  # tries to let you output the various things that can be set.
#   quit  #closes hackvr only if the id that is doing it is the same as yours.
#   set
#   physics
#   control grou* [globbing this group could have fun effects]
#   addshape color N x1 y1 z1 ... xN yN zN
#   export grou*
#   ping any-string-without-spaces
# * scale x y z
# * rotate [+]x [+]y [+]z
#   periodic  # flushes out locally-cached movement and rotation
#   flatten  # combines group attributes to the shapes.
# * move [+]x [+]y [+]z
# * move forward|backward|up|down|left|right
hackvr also outputs

name action targetgroup
when a group is clicked on using the name set from the command line. usually $USER
Here's some of the crap I've had hackvr do:


so, this first converts an obj to hackvr format, appends a line to rescale it, and then export it



## Changes

- Encoding is assumed UTF-8
- Max. line length excluding the `\n` is 1024 bytes