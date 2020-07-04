# hackvr-turbo

Implementation of [epochs HackVR](https://github.com/kkabrams/hackvr) project.

[![](https://mq32.de/public/1e394016e7c7292bb661299a912266a0d1a79182.png
)](https://mq32.de/public/hackvr-05.mp4)

## Current status

- Basic rendering works
- Commands implemented:
  - `addshape`
  - `move` (partially)
  - `rotate` (partially)
  - `renamegroup`
- Std-I/O works

## Controls

Use *Up* and *Down* to move forward/backward, *Left* and *Right* to rotate the camera. Use *Alt* to change *Left*/*Right* to strafing.
*W*,*A*,*S*,*D* can also be used to move the camera (strafing + forward).

With *Page Up* and *Page Down* you can look up/down, using *Alt* allows to move the camera up or down.

Right click with the mouse and drag to rotate the camera. Use the left mouse button to trigger a `action` output to stdout.

## Quick Start

Build the project (see below), then run this:
```sh
cat ./lib/hackvr/data/test.hackvr | ./zig-cache/bin/hackvr
```

## References
- https://github.com/kkabrams/hackvr 
- https://thebackupbox.net/cgi-bin/pageview.cgi?page=hackvr

## Dependencies / Building

Provide the following packages on your system:
- SDL2
- libepoxy

Use [zig](https://ziglang.org/download/) `master` to build the project:
```sh
git submodule update --init --recursive
zig build
```

After compiling, use `zig build run` to start the HackVR executable