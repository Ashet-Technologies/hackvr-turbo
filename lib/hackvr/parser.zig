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

    pub fn init() Parser {
        return Parser{
            .line_buffer = undefined,
            .line_offset = 0,
        };
    }

    fn parseLine(line: []const u8) !?Event {
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
                    const event = parseLine(line) catch |err| switch (err) {
                        error.UnknownCommand => return PushResult{
                            .parse_error = .{
                                .rest = rest,
                                .error_type = .unknown_command,
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
        event: ?Event,
    },

    /// A format error happened while processing the data.
    parse_error: struct {
        const Error = enum {
            syntax_error,
            invalid_format,
            unknown_command,
        };

        /// The portion of the input data that was not parsed
        /// while encountering this event.
        /// Feed it into `push` again until .needs_data happens.
        rest: []const u8,

        /// The error that was encountered
        error_type: Error,
    },
};

pub const EventType = enum {
    help,
    version,
    status,
    dump,
    quit,
    set,
    physics,
    control,
    addshape,
    @"export",
    ping,
    scale,
    rotate,
    periodic,
    flatten,
    move,
    delete_group,
    assimilate,
    rename_group,
    delete_all_except,
};

pub const Selector = struct {
    groups: []const u8,
};

pub const GroupArgSelector = struct {
    selector: Selector,
    groups: []const u8,
};

pub const Event = union(EventType) {
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
    addshape,
    @"export": GroupArgSelector,
    ping,
    scale,
    rotate,
    periodic: Selector,
    flatten: Selector,
    move,
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
    _ = Parser.parseLine("  a bb cccc ") catch |err| {
        std.testing.expect(err == error.UnknownCommand);
        return;
    };
    unreachable;
}

test "parser: cmd help" {
    const result = (try Parser.parseLine("help")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .help);
}

test "parser: cmd version" {
    const result = (try Parser.parseLine("version")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .version);
}

test "parser: cmd status" {
    const result = (try Parser.parseLine("foobar status")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .status);
    std.testing.expectEqualStrings("foobar", result.status.groups);
}

test "parser: cmd dump" {
    const result = (try Parser.parseLine("foobar dump")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .dump);
    std.testing.expectEqualStrings("foobar", result.dump.groups);
}

test "parser: cmd quit" {
    const result = (try Parser.parseLine("foobar quit")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .quit);
    std.testing.expectEqualStrings("foobar", result.quit.groups);
}

test "parser: cmd set" {
    const result = (try Parser.parseLine("foobar set")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .set);
    std.testing.expectEqualStrings("foobar", result.set.groups);
}

test "parser: cmd physics" {
    const result = (try Parser.parseLine("foobar physics")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .physics);
    std.testing.expectEqualStrings("foobar", result.physics.groups);
}

test "parser: cmd periodic" {
    const result = (try Parser.parseLine("foobar periodic")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .periodic);
    std.testing.expectEqualStrings("foobar", result.periodic.groups);
}

test "parser: cmd flatten" {
    const result = (try Parser.parseLine("foobar flatten")) orelse return error.ExpectedEvent;
    std.testing.expect(result == .flatten);
    std.testing.expectEqualStrings("foobar", result.flatten.groups);
}

test "parser: cmd deleteallexcept" {
    const result = (try Parser.parseLine("foobar deleteallexcept groupsel")) orelse return error.ExpectedEvent;

    std.testing.expect(result == .delete_all_except);
    std.testing.expectEqualStrings("foobar", result.delete_all_except.selector.groups);
    std.testing.expectEqualStrings("groupsel", result.delete_all_except.groups);
}

test "parser: cmd delete_group" {
    const result = (try Parser.parseLine("foobar deletegroup groupsel")) orelse return error.ExpectedEvent;

    std.testing.expect(result == .delete_group);
    std.testing.expectEqualStrings("foobar", result.delete_group.selector.groups);
    std.testing.expectEqualStrings("groupsel", result.delete_group.groups);
}

test "parser: cmd delete_group" {
    const result = (try Parser.parseLine("foobar renamegroup groupsel")) orelse return error.ExpectedEvent;

    std.testing.expect(result == .rename_group);
    std.testing.expectEqualStrings("foobar", result.rename_group.selector.groups);
    std.testing.expectEqualStrings("groupsel", result.rename_group.groups);
}

test "parser: cmd delete_group" {
    const result = (try Parser.parseLine("foobar assimilate groupsel")) orelse return error.ExpectedEvent;

    std.testing.expect(result == .assimilate);
    std.testing.expectEqualStrings("foobar", result.assimilate.selector.groups);
    std.testing.expectEqualStrings("groupsel", result.assimilate.groups);
}

test "parser: cmd control" {
    const result = (try Parser.parseLine("foobar control groupsel")) orelse return error.ExpectedEvent;

    std.testing.expect(result == .control);
    std.testing.expectEqualStrings("foobar", result.control.selector.groups);
    std.testing.expectEqualStrings("groupsel", result.control.groups);
}

test "parser: cmd export" {
    const result = (try Parser.parseLine("foobar export groupsel")) orelse return error.ExpectedEvent;

    std.testing.expect(result == .@"export");
    std.testing.expectEqualStrings("foobar", result.@"export".selector.groups);
    std.testing.expectEqualStrings("groupsel", result.@"export".groups);
}
