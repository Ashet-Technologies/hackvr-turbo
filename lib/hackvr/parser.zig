const std = @import("std");

const hvr = @import("lib.zig");

const FixedList = @import("fixed-list").FixedList;

/// A push-event based parser for HackVR input.
/// Parses hackvr text into serialized, preparsed commands.
/// It's not interactive and can eat any amount of data.
/// When the parser encounters a line feed, it will process the
/// line and return a Event or fail with "unknown command"
pub const Parser = struct {
    const Self = @This();

    line_buffer: [1024]u8,
    line_offset: usize,

    point_buffer: [16]hvr.Vec3D,

    pub fn init() Parser {
        return Parser{
            .line_buffer = undefined,
            .line_offset = 0,
            .point_buffer = undefined,
        };
    }

    fn parseLine(self: *Parser, line: []const u8) !?Event {
        // max number of slices separated by a
        var items = FixedList([]const u8, 512).init();

        {
            var current_start: usize = 0;
            for (line) |c, i| {
                if (std.ascii.isSpace(c)) {
                    if (current_start < i) {
                        try items.append(line[current_start..i]);
                    }
                    current_start = i + 1;
                } else if (c == '#') {
                    // rest is comment
                    current_start = line.len;
                    break;
                }
            }
            if (current_start < line.len) {
                try items.append(line[current_start..]);
            }
        }

        switch (items.count) {
            0 => return null,
            1 => {
                if (std.mem.eql(u8, "help", items.buffer[0])) {
                    return Event{ .help = {} };
                } else if (std.mem.eql(u8, "version", items.buffer[0])) {
                    return Event{ .version = {} };
                } else {
                    return error.UnknownCommand;
                }
            },
            else => {
                const selector = Selector{
                    .groups = items.buffer[0],
                };
                const cmd = items.buffer[1];
                const args = items.span()[2..];

                if (std.mem.eql(u8, cmd, "status")) {
                    return Event{ .status = selector };
                } else if (std.mem.eql(u8, cmd, "dump")) {
                    return Event{ .dump = selector };
                } else if (std.mem.eql(u8, cmd, "quit")) {
                    return Event{ .quit = selector };
                } else if (std.mem.eql(u8, cmd, "set")) {
                    return Event{ .set = selector };
                } else if (std.mem.eql(u8, cmd, "physics")) {
                    return Event{ .physics = selector };
                } else if (std.mem.eql(u8, cmd, "periodic")) {
                    return Event{ .periodic = selector };
                } else if (std.mem.eql(u8, cmd, "flatten")) {
                    return Event{ .flatten = selector };
                } else if (std.mem.eql(u8, cmd, "deleteallexcept")) {
                    if (args.len != 1)
                        return error.ArgumentMismatch;
                    return Event{
                        .delete_all_except = GroupArgSelector{
                            .selector = selector,
                            .groups = args[0],
                        },
                    };
                } else if (std.mem.eql(u8, cmd, "deletegroup")) {
                    if (args.len != 1)
                        return error.ArgumentMismatch;
                    return Event{
                        .delete_group = GroupArgSelector{
                            .selector = selector,
                            .groups = args[0],
                        },
                    };
                } else if (std.mem.eql(u8, cmd, "assimilate")) {
                    if (args.len != 1)
                        return error.ArgumentMismatch;
                    return Event{
                        .assimilate = GroupArgSelector{
                            .selector = selector,
                            .groups = args[0],
                        },
                    };
                } else if (std.mem.eql(u8, cmd, "renamegroup")) {
                    if (args.len != 1)
                        return error.ArgumentMismatch;
                    return Event{
                        .rename_group = GroupArgSelector{
                            .selector = selector,
                            .groups = args[0],
                        },
                    };
                } else if (std.mem.eql(u8, cmd, "export")) {
                    if (args.len != 1)
                        return error.ArgumentMismatch;
                    return Event{
                        .@"export" = GroupArgSelector{
                            .selector = selector,
                            .groups = args[0],
                        },
                    };
                } else if (std.mem.eql(u8, cmd, "control")) {
                    if (args.len != 1)
                        return error.ArgumentMismatch;
                    return Event{
                        .control = GroupArgSelector{
                            .selector = selector,
                            .groups = args[0],
                        },
                    };
                } else if (std.mem.eql(u8, cmd, "addshape")) {
                    if (args.len < 2)
                        return error.ArgumentMismatch;
                    const color = try std.fmt.parseInt(u8, args[0], 10);
                    const argc = try std.fmt.parseInt(usize, args[1], 10);

                    if (args.len != (2 + 3 * argc))
                        return error.ArgumentMismatch;

                    const slice = self.point_buffer[0..argc];

                    for (slice) |*item, i| {
                        const off = 2 + 3 * i;
                        item.x = try std.fmt.parseFloat(hvr.real, args[off + 0]);
                        item.y = try std.fmt.parseFloat(hvr.real, args[off + 1]);
                        item.z = try std.fmt.parseFloat(hvr.real, args[off + 2]);
                    }

                    return Event{
                        .add_shape = AddShapeData{
                            .selector = selector,
                            .color = color,
                            .polygon = slice,
                        },
                    };
                } else if (std.mem.eql(u8, cmd, "ping")) {
                    if (args.len != 1)
                        return error.ArgumentMismatch;
                    return Event{
                        .ping = PingData{
                            .selector = selector,
                            .ping_target = args[0],
                        },
                    };
                } else if (std.mem.eql(u8, cmd, "scale")) {
                    if (args.len != 3)
                        return error.ArgumentMismatch;
                    return Event{
                        .scale = ScaleData{
                            .selector = selector,
                            .scale = hvr.Vec3D{
                                .x = try std.fmt.parseFloat(hvr.real, args[0]),
                                .y = try std.fmt.parseFloat(hvr.real, args[1]),
                                .z = try std.fmt.parseFloat(hvr.real, args[2]),
                            },
                        },
                    };
                } else if (std.mem.eql(u8, cmd, "rotate")) {
                    if (args.len != 3)
                        return error.ArgumentMismatch;
                    return Event{
                        .rotate = AbsRelVectorData{
                            .selector = selector,
                            .vector = AbsRelVector{
                                .x = try AbsRel.parse(args[0]),
                                .y = try AbsRel.parse(args[1]),
                                .z = try AbsRel.parse(args[2]),
                            },
                        },
                    };
                } else if (std.mem.eql(u8, cmd, "move")) {
                    switch (args.len) {
                        1 => {
                            var dir = if (std.mem.eql(u8, args[0], "forward"))
                                MoveData.Direction{ .forward = {} }
                            else if (std.mem.eql(u8, args[0], "backward"))
                                MoveData.Direction{ .backward = {} }
                            else if (std.mem.eql(u8, args[0], "up"))
                                MoveData.Direction{ .up = {} }
                            else if (std.mem.eql(u8, args[0], "down"))
                                MoveData.Direction{ .down = {} }
                            else if (std.mem.eql(u8, args[0], "left"))
                                MoveData.Direction{ .left = {} }
                            else if (std.mem.eql(u8, args[0], "right"))
                                MoveData.Direction{ .right = {} }
                            else
                                return error.InvalidArgument;

                            return Event{
                                .move = MoveData{
                                    .selector = selector,
                                    .direction = dir,
                                },
                            };
                        },
                        3 => {
                            return Event{
                                .move = MoveData{
                                    .selector = selector,
                                    .direction = .{
                                        .offset = AbsRelVector{
                                            .x = try AbsRel.parse(args[0]),
                                            .y = try AbsRel.parse(args[1]),
                                            .z = try AbsRel.parse(args[2]),
                                        },
                                    },
                                },
                            };
                        },

                        else => return error.ArgumentMismatch,
                    }
                }
                return error.UnknownCommand;
            },
        }
    }

    /// Pushes data into the parser.
    pub fn push(self: *Self, source: []const u8) !PushResult {
        var offset: usize = 0;

        while (offset < source.len) {
            if (source[offset] == '\n') {
                var line = self.line_buffer[0..self.line_offset];
                self.line_offset = 0;
                offset += 1;

                if (line.len > 0 and line[line.len - 1] == '\r') {
                    // strip off CR
                    line = line[0 .. line.len - 1];
                }

                if (!std.unicode.utf8ValidateSlice(line))
                    return error.InvalidEncoding;

                const rest = source[offset..];

                if (line.len > 0) {
                    const event = self.parseLine(line) catch |err| switch (err) {
                        error.UnknownCommand => return PushResult{
                            .parse_error = .{
                                .source = line,
                                .rest = rest,
                                .error_type = .unknown_command,
                            },
                        },
                        error.ArgumentMismatch => return PushResult{
                            .parse_error = .{
                                .source = line,
                                .rest = rest,
                                .error_type = .argument_mismatch,
                            },
                        },
                        else => return err,
                    };

                    if (event) |ev| {
                        return PushResult{
                            .event = .{
                                .rest = rest,
                                .event = ev,
                            },
                        };
                    }
                }
            } else {
                if (self.line_offset > self.line_buffer.len)
                    return error.OutOfMemory;
                self.line_buffer[self.line_offset] = source[offset];
                self.line_offset += 1;
                offset += 1;
            }
        }

        return PushResult{
            .needs_data = {},
        };
    }
};

/// Result of a push operation on the Parser.
/// Will contain information on how to proceed with the stream.
pub const PushResult = union(enum) {
    /// input was completly consumed, no event happened
    needs_data,

    /// An event happend while processing the data.
    event: struct {
        /// The portion of the input data that was not parsed
        /// while encountering this event.
        /// Feed it into `push` again until .needs_data happens.
        rest: []const u8,

        event: Event,
    },

    /// A format error happened while processing the data.
    parse_error: struct {
        const Error = enum {
            syntax_error,
            invalid_format,
            unknown_command,
            argument_mismatch,
        };

        /// The portion that triggered the error.
        source: []const u8,

        /// The portion of the input data that was not parsed
        /// while encountering this event.
        /// Feed it into `push` again until .needs_data happens.
        rest: []const u8,

        /// The error that was encountered
        error_type: Error,
    },
};

pub const AbsRel = union(enum) {
    const Self = @This();

    absolute: hvr.real,
    relative: hvr.real,

    fn parse(str: []const u8) !AbsRel {
        std.debug.assert(str.len > 0);
        if (str[0] == '+') {
            return AbsRel{
                .relative = try std.fmt.parseFloat(hvr.real, str[1..]),
            };
        } else {
            return AbsRel{
                .absolute = try std.fmt.parseFloat(hvr.real, str),
            };
        }
    }

    /// Applies the value to a previous value
    pub fn apply(self: Self, in: hvr.real) hvr.real {
        return switch (self) {
            .relative => |v| in + v,
            .absolute => |v| v,
        };
    }
};

pub const AbsRelVector = struct {
    const Self = @This();

    x: AbsRel,
    y: AbsRel,
    z: AbsRel,

    pub fn apply(self: Self, v3d: hvr.Vec3D) hvr.Vec3D {
        return .{
            .x = self.x.apply(v3d.x),
            .y = self.y.apply(v3d.y),
            .z = self.z.apply(v3d.z),
        };
    }
};

pub const Selector = struct {
    groups: []const u8,
};

pub const GroupArgSelector = struct {
    selector: Selector,
    groups: []const u8,
};

pub const AddShapeData = struct {
    selector: Selector,
    color: u8,
    polygon: []const hvr.Vec3D,
};

pub const ScaleData = struct {
    selector: Selector,
    scale: hvr.Vec3D,
};

pub const AbsRelVectorData = struct {
    selector: Selector,
    vector: AbsRelVector,
};

pub const MoveData = struct {
    const Type = @TagType(Direction);
    const Direction = union(enum) {
        forward,
        backward,
        left,
        right,
        up,
        down,
        offset: AbsRelVector,
    };

    selector: Selector,
    direction: Direction,
};

pub const PingData = struct {
    selector: Selector,
    ping_target: []const u8,
};

pub const EventType = @TagType(Event);
pub const Event = union(enum) {
    delete_group: GroupArgSelector,
    assimilate: GroupArgSelector,
    rename_group: GroupArgSelector,
    delete_all_except: GroupArgSelector,
    help,
    version,
    status: Selector,
    dump: Selector,
    quit: Selector,
    set: Selector,
    physics: Selector,
    control: GroupArgSelector,
    add_shape: AddShapeData,
    @"export": GroupArgSelector,
    ping: PingData,
    scale: ScaleData,
    rotate: AbsRelVectorData,
    periodic: Selector,
    flatten: Selector,
    move: MoveData,
};

test "parser: invalid encoding" {
    var parser = Parser.init();

    _ = parser.push("\xFF\n") catch |err| {
        std.testing.expect(err == error.InvalidEncoding);
        return;
    };
    unreachable;
}

test "parser: empty" {
    var parser = Parser.init();

    const result = try parser.push("");
    std.testing.expect(result == .needs_data);
}

test "parser: whitespace lines" {
    var parser = Parser.init();

    const result = try parser.push("\n   \n\n  \n \n \n\n\n    \n");
    std.testing.expect(result == .needs_data);
}

test "parser: ParseResult.rest/error" {
    var parser = Parser.init();

    const result = try parser.push("a\nb");
    std.testing.expect(result == .parse_error);
    std.testing.expectEqualStrings("b", result.parse_error.rest);
    std.testing.expect(result.parse_error.error_type == .unknown_command);
}

test "parser: ParseResult.rest/event" {
    var parser = Parser.init();

    const result = try parser.push("help\nb");
    std.testing.expect(result == .event);
    std.testing.expectEqualStrings("b", result.event.rest);
}

test "parser: parse line" {
    _ = Parser.init().parseLine("  a bb cccc ") catch |err| {
        std.testing.expect(err == error.UnknownCommand);
        return;
    };
    unreachable;
}

test "parser: cmd help" {
    const result = (try Parser.init().parseLine("help")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .help);
}

test "parser: cmd version" {
    const result = (try Parser.init().parseLine("version")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .version);
}

test "parser: cmd status" {
    const result = (try Parser.init().parseLine("foobar status")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .status);
    std.testing.expectEqualStrings("foobar", result.status.groups);
}

test "parser: cmd dump" {
    const result = (try Parser.init().parseLine("foobar dump")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .dump);
    std.testing.expectEqualStrings("foobar", result.dump.groups);
}

test "parser: cmd quit" {
    const result = (try Parser.init().parseLine("foobar quit")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .quit);
    std.testing.expectEqualStrings("foobar", result.quit.groups);
}

test "parser: cmd set" {
    const result = (try Parser.init().parseLine("foobar set")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .set);
    std.testing.expectEqualStrings("foobar", result.set.groups);
}

test "parser: cmd physics" {
    const result = (try Parser.init().parseLine("foobar physics")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .physics);
    std.testing.expectEqualStrings("foobar", result.physics.groups);
}

test "parser: cmd periodic" {
    const result = (try Parser.init().parseLine("foobar periodic")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .periodic);
    std.testing.expectEqualStrings("foobar", result.periodic.groups);
}

test "parser: cmd flatten" {
    const result = (try Parser.init().parseLine("foobar flatten")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .flatten);
    std.testing.expectEqualStrings("foobar", result.flatten.groups);
}

test "parser: cmd deleteallexcept" {
    const result = (try Parser.init().parseLine("foobar deleteallexcept groupsel")) orelse return error.ExpectedEvent;

    std.testing.expect(result == .delete_all_except);
    std.testing.expectEqualStrings("foobar", result.delete_all_except.selector.groups);
    std.testing.expectEqualStrings("groupsel", result.delete_all_except.groups);
}

test "parser: cmd delete_group" {
    const result = (try Parser.init().parseLine("foobar deletegroup groupsel")) orelse return error.ExpectedEvent;

    std.testing.expect(result == .delete_group);
    std.testing.expectEqualStrings("foobar", result.delete_group.selector.groups);
    std.testing.expectEqualStrings("groupsel", result.delete_group.groups);
}

test "parser: cmd delete_group" {
    const result = (try Parser.init().parseLine("foobar renamegroup groupsel")) orelse return error.ExpectedEvent;

    std.testing.expect(result == .rename_group);
    std.testing.expectEqualStrings("foobar", result.rename_group.selector.groups);
    std.testing.expectEqualStrings("groupsel", result.rename_group.groups);
}

test "parser: cmd delete_group" {
    const result = (try Parser.init().parseLine("foobar assimilate groupsel")) orelse return error.ExpectedEvent;

    std.testing.expect(result == .assimilate);
    std.testing.expectEqualStrings("foobar", result.assimilate.selector.groups);
    std.testing.expectEqualStrings("groupsel", result.assimilate.groups);
}

test "parser: cmd control" {
    const result = (try Parser.init().parseLine("foobar control groupsel")) orelse return error.ExpectedEvent;

    std.testing.expect(result == .control);
    std.testing.expectEqualStrings("foobar", result.control.selector.groups);
    std.testing.expectEqualStrings("groupsel", result.control.groups);
}

test "parser: cmd export" {
    const result = (try Parser.init().parseLine("foobar export groupsel")) orelse return error.ExpectedEvent;

    std.testing.expect(result == .@"export");
    std.testing.expectEqualStrings("foobar", result.@"export".selector.groups);
    std.testing.expectEqualStrings("groupsel", result.@"export".groups);
}

test "parser: cmd addshape" {
    var parser = Parser.init();

    {
        const result = (try parser.parseLine("foobar addshape 3 0")) orelse return error.ExpectedEvent;

        std.testing.expect(result == .add_shape);
        std.testing.expectEqualStrings("foobar", result.add_shape.selector.groups);
        std.testing.expectEqual(@as(u8, 3), result.add_shape.color);
        std.testing.expectEqualSlices(
            hvr.Vec3D,
            &[_]hvr.Vec3D{},
            result.add_shape.polygon,
        );
    }

    {
        const result = (try parser.parseLine("foobar addshape 3 1 1.5 2.5 3.5")) orelse return error.ExpectedEvent;

        std.testing.expect(result == .add_shape);
        std.testing.expectEqualStrings("foobar", result.add_shape.selector.groups);
        std.testing.expectEqual(@as(u8, 3), result.add_shape.color);
        std.testing.expectEqualSlices(
            hvr.Vec3D,
            &[_]hvr.Vec3D{
                .{ .x = 1.5, .y = 2.5, .z = 3.5 },
            },
            result.add_shape.polygon,
        );
    }

    {
        const result = (try parser.parseLine("foobar addshape 3 2 1.5 2.5 3.5 7 8 132213.3")) orelse return error.ExpectedEvent;

        std.testing.expect(result == .add_shape);
        std.testing.expectEqualStrings("foobar", result.add_shape.selector.groups);
        std.testing.expectEqual(@as(u8, 3), result.add_shape.color);
        std.testing.expectEqualSlices(
            hvr.Vec3D,
            &[_]hvr.Vec3D{
                .{ .x = 1.5, .y = 2.5, .z = 3.5 },
                .{ .x = 7.0, .y = 8.0, .z = 132213.3 },
            },
            result.add_shape.polygon,
        );
    }
}

test "parser: cmd ping" {
    const result = (try Parser.init().parseLine("foobar ping long.text.without.spaces")) orelse return error.ExpectedEvent;

    std.testing.expect(result == .ping);
    std.testing.expectEqualStrings("foobar", result.ping.selector.groups);
    std.testing.expectEqualStrings("long.text.without.spaces", result.ping.ping_target);
}

test "parser: cmd scale" {
    const result = (try Parser.init().parseLine("foobar scale 1.4 -2.3 1.8")) orelse return error.ExpectedEvent;

    std.testing.expect(result == .scale);
    std.testing.expectEqualStrings("foobar", result.scale.selector.groups);
    std.testing.expectEqual(hvr.Vec3D{ .x = 1.4, .y = -2.3, .z = 1.8 }, result.scale.scale);
}

test "parser: cmd rotate" {
    const result = (try Parser.init().parseLine("foobar rotate +1.4 -2.25 +-1.8")) orelse return error.ExpectedEvent;

    std.testing.expect(result == .rotate);
    std.testing.expectEqualStrings("foobar", result.rotate.selector.groups);
    std.testing.expectEqual(AbsRelVector{
        .x = AbsRel{ .relative = 1.4 },
        .y = AbsRel{ .absolute = -2.25 },
        .z = AbsRel{ .relative = -1.8 },
    }, result.rotate.vector);
}

test "parser: cmd move" {
    var parser = Parser.init();

    {
        const result = (try parser.parseLine("foobar move +1.4 -2.3 +-1.8")) orelse return error.ExpectedEvent;

        std.testing.expect(result == .move);
        std.testing.expectEqualStrings("foobar", result.move.selector.groups);
        std.testing.expectEqual(MoveData.Type.offset, result.move.direction);
        std.testing.expectEqual(AbsRelVector{
            .x = AbsRel{ .relative = 1.4 },
            .y = AbsRel{ .absolute = -2.3 },
            .z = AbsRel{ .relative = -1.8 },
        }, result.move.direction.offset);
    }

    {
        const result = (try parser.parseLine("foobar move forward")) orelse return error.ExpectedEvent;

        std.testing.expect(result == .move);
        std.testing.expectEqualStrings("foobar", result.move.selector.groups);
        std.testing.expectEqual(MoveData.Type.forward, result.move.direction);
    }

    {
        const result = (try parser.parseLine("foobar move backward")) orelse return error.ExpectedEvent;

        std.testing.expect(result == .move);
        std.testing.expectEqualStrings("foobar", result.move.selector.groups);
        std.testing.expectEqual(MoveData.Type.backward, result.move.direction);
    }

    {
        const result = (try parser.parseLine("foobar move right")) orelse return error.ExpectedEvent;

        std.testing.expect(result == .move);
        std.testing.expectEqualStrings("foobar", result.move.selector.groups);
        std.testing.expectEqual(MoveData.Type.right, result.move.direction);
    }

    {
        const result = (try parser.parseLine("foobar move left")) orelse return error.ExpectedEvent;

        std.testing.expect(result == .move);
        std.testing.expectEqualStrings("foobar", result.move.selector.groups);
        std.testing.expectEqual(MoveData.Type.left, result.move.direction);
    }

    {
        const result = (try parser.parseLine("foobar move up")) orelse return error.ExpectedEvent;

        std.testing.expect(result == .move);
        std.testing.expectEqualStrings("foobar", result.move.selector.groups);
        std.testing.expectEqual(MoveData.Type.up, result.move.direction);
    }

    {
        const result = (try parser.parseLine("foobar move down")) orelse return error.ExpectedEvent;

        std.testing.expect(result == .move);
        std.testing.expectEqualStrings("foobar", result.move.selector.groups);
        std.testing.expectEqual(MoveData.Type.down, result.move.direction);
    }
}

test "parser: whole file" {
    var parser = Parser.init();

    var src: []const u8 = @embedFile("./data/test.hackvr");

    while (src.len > 0) {
        var item = try parser.push(src);
        switch (item) {
            // should never be reached as the test.hackvr is a complete file, terminated by a LF
            .needs_data => unreachable,

            // should never be reached as the test.hackvr file is correct
            .parse_error => unreachable,

            .event => |ev| {
                src = ev.rest;
                // std.log.debug(.HackVR, "event: {}\n", .{ev.event});
            },
        }
    }
}
