const std = @import("std");

const hvr = @import("lib.zig");

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

    /// Pushes data into the parser.
    pub fn push(self: *Self, source: []const u8) !PushResult {
        var offset: usize = 0;

        while (offset < source.len) {
            defer offset += 1;
            if (source[offset] == '\n') {
                var line = self.line_buffer[0..self.line_offset];
                if (!std.unicode.utf8ValidateSlice(line))
                    return error.InvalidEncoding;

                std.log.debug(.HackVR, "Emit event for line '{}'\n", .{line});

                return PushResult{
                    .event = .{
                        .rest = source[0..offset],
                        .event = Event{},
                    },
                };
            }

            if (self.line_offset > self.line_buffer.len)
                return error.OutOfMemory;
            self.line_buffer[self.line_offset] = source[offset];
            self.line_offset += 1;
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
        };

        /// The portion of the input data that was not parsed
        /// while encountering this event.
        /// Feed it into `push` again until .needs_data happens.
        rest: []const u8,

        /// The error that was encountered
        error_type: Error,
    },
};

pub const Event = struct {};

test "parser: invalid encoding" {
    var parser = Parser.init();

    _ = parser.push("\xFF\n") catch |err| {
        std.testing.expect(err == error.InvalidEncoding);
        return;
    };
    unreachable;
}
