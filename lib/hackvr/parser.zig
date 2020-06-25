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
                    return Event{
                        .event_type = .help,
                    };
                } else if (std.mem.eql(u8, "version", items.buffer[0])) {
                    return Event{
                        .event_type = .version,
                    };
                } else {
                    return error.UnknownCommand;
                }
            },
            else => {
                return Event{
                    .event_type = .not_implemented_yet,
                };
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

pub const Event = struct {
    const Type = enum {
        help,
        version,

        not_implemented_yet,
    };

    event_type: Type,
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
    _ = try Parser.parseLine("  a bb cccc ");
}

test "parser: cmd help" {
    const result = (try Parser.parseLine("help")) orelse return error.ExpectedEvent;
    std.testing.expect(result.event_type == .help);
}

test "parser: cmd version" {
    const result = (try Parser.parseLine("version")) orelse return error.ExpectedEvent;
    std.testing.expect(result.event_type == .version);
}
