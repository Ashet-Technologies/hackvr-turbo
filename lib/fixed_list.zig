const std = @import("std");

pub fn FixedList(comptime T: type, comptime limit: usize) type {
    return struct {
        const Self = @This();

        buffer: [limit]T,
        count: usize,

        pub fn init() Self {
            return Self{
                .buffer = undefined,
                .count = 0,
            };
        }

        pub fn append(self: *Self, value: T) !void {
            if (self.count >= limit)
                return error.OutOfMemory;
            self.buffer[self.count] = value;
            self.count += 1;
        }

        pub fn pop(self: *Self) ?T {
            if (self.count > 0) {
                self.count -= 1;
                var value = self.buffer[self.count];
                self.buffer[self.count] = undefined;
                return value;
            } else {
                return null;
            }
        }

        /// Return contents as a slice. Only valid while the list
        /// doesn't change size.
        pub fn span(self: *Self) []T {
            return self.buffer[0..self.count];
        }
    };
}
