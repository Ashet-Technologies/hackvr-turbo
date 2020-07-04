const std = @import("std");
const zlm = @import("zlm");

pub const parsing = @import("parser.zig");

comptime {
    // include the parser module for tests
    _ = parsing;
}

pub const real = f32;

pub const Vec3D = zlm.Vec3;

pub const Attribute = struct {
    color: u8, //color. not sure how I plan on using this.
    luminance: u8, //brightness. 1 - 200 atm because X11 has grey1 - grey200
};

pub const Shape3D = struct {
    /// index into State.groups
    group: usize,
    points: []Vec3D,
    velocity: Vec3D,
    attributes: Attribute,
};

pub const Group = struct {
    const Self = @This();

    name: []const u8,

    /// flat list of all shapes
    shapes: std.ArrayList(Shape3D),

    translation: zlm.Vec3,
    rotation: zlm.Vec3,

    pub fn init(allocator: *std.mem.Allocator, name: []const u8) Self {
        return Self{
            .name = name,
            .shapes = std.ArrayList(Shape3D).init(allocator),
            .translation = zlm.Vec3.zero,
            .rotation = zlm.Vec3.zero,
        };
    }

    pub fn deinit(self: *Self) void {
        self.shapes.deinit();
        self.* = undefined;
    }
};

pub const State = struct {
    const Self = @This();

    allocator: *std.mem.Allocator,

    /// storage for shape vertices and group names
    arena: std.heap.ArenaAllocator,

    /// flat list of all groups
    groups: std.ArrayList(Group),

    pub fn init(allocator: *std.mem.Allocator) Self {
        return Self{
            .allocator = allocator,
            .arena = std.heap.ArenaAllocator.init(allocator),
            .groups = std.ArrayList(Group).init(allocator),
        };
    }

    pub fn deinit(self: *Self) void {
        for (self.groups.items) |*group| {
            group.deinit();
        }
        self.groups.deinit();
        self.arena.deinit();
        self.* = undefined;
    }

    pub fn getOrCreateGroup(self: *Self, name: []const u8) !*Group {
        for (self.groups.items) |*grp| {
            if (std.mem.eql(u8, grp.name, name)) {
                return grp;
            }
        }

        const name_ptr = try std.mem.dupe(&self.arena.allocator, u8, name);
        errdefer self.allocator.free(name_ptr);

        const grp = try self.groups.addOne();
        grp.* = Group.init(self.allocator, name_ptr);
        return grp;
    }

    /// Returns an iterator yielding all groups.
    pub fn iterator(self: *Self) GroupIterator {
        return GroupIterator{
            .state = self,
            .index = 0,
            .pattern = null,
        };
    }

    /// Returns an iterator yielding all groups that match the pattern.
    pub fn findGroups(self: *Self, pattern: []const u8) GroupIterator {
        return GroupIterator{
            .state = self,
            .index = 0,
            .pattern = pattern,
        };
    }

    pub const GroupIterator = struct {
        state: *Self,
        index: usize,
        pattern: ?[]const u8,

        pub fn next(self: *@This()) ?*Group {
            while (self.index < self.state.groups.items.len) {
                const grp = &self.state.groups.items[self.index];
                self.index += 1;

                if (self.pattern) |pattern| {
                    if (!wildcardEquals(pattern, grp.name))
                        continue;
                }
                return grp;
            }
            return null;
        }
    };
};

pub fn applyEventToState(state: *State, event: parsing.Event) !void {
    switch (event) {
        .add_shape => |cmd| {
            if (isWildcardPattern(cmd.selector.groups))
                return error.InvalidSelector;

            const grp = try state.getOrCreateGroup(cmd.selector.groups);

            const index = grp.shapes.items.len;

            const shp = try grp.shapes.addOne();
            errdefer {
                // Remove the newly created shape
                _ = grp.shapes.pop();
            }

            shp.* = Shape3D{
                .group = index,
                .velocity = Vec3D{ .x = 0, .y = 0, .z = 0 },
                .attributes = Attribute{
                    .color = cmd.color,
                    .luminance = 200,
                },
                .points = try std.mem.dupe(&state.arena.allocator, Vec3D, cmd.polygon),
            };
        },
        .move => |cmd| {
            var iter = state.findGroups(cmd.selector.groups);
            while (iter.next()) |grp| {
                switch (cmd.direction) {
                    .offset => |offset| {
                        grp.translation = offset.apply(grp.translation);
                    },
                    else => std.debug.panic("relative movement not implemented yet", .{}),
                }
            }
        },
        .rotate => |cmd| {
            var iter = state.findGroups(cmd.selector.groups);
            while (iter.next()) |grp| {
                grp.rotation = cmd.vector.apply(grp.rotation);
            }
        },
        .rename_group => |cmd| {
            var new_name = try std.mem.dupe(&state.arena.allocator, u8, cmd.groups);

            var iter = state.findGroups(cmd.selector.groups);
            while (iter.next()) |grp| {
                grp.name = new_name;
            }
        },
        else => {
            std.debug.print("Event {} not implemented yet!\n", .{@as(parsing.EventType, event)});
        },
    }
}

test "State.iterator" {
    var state = State.init(std.testing.allocator);
    defer state.deinit();

    const grp1 = try state.getOrCreateGroup("grp1");
    const grp2 = try state.getOrCreateGroup("grp2");
    const grp3 = try state.getOrCreateGroup("grp3");

    var found1 = false;
    var found2 = false;
    var found3 = false;

    var iter = state.iterator();
    while (iter.next()) |grp| {
        if (grp == grp1) {
            std.testing.expectEqual(false, found1);
            found1 = true;
        }
        if (grp == grp2) {
            std.testing.expectEqual(false, found2);
            found2 = true;
        }
        if (grp == grp3) {
            std.testing.expectEqual(false, found3);
            found3 = true;
        }
    }

    std.testing.expect(found1 and found2 and found3);
}

test "State.findGroups" {
    var state = State.init(std.testing.allocator);
    defer state.deinit();

    const grp1 = try state.getOrCreateGroup("a_1");
    const grp2 = try state.getOrCreateGroup("a_2");
    const grp3 = try state.getOrCreateGroup("b_1");

    var found1 = false;
    var found2 = false;
    var found3 = false;

    var iter = state.findGroups("a*");
    while (iter.next()) |grp| {
        if (grp == grp1) {
            std.testing.expectEqual(false, found1);
            found1 = true;
        }
        if (grp == grp2) {
            std.testing.expectEqual(false, found2);
            found2 = true;
        }
        if (grp == grp3) {
            std.testing.expect(false);
        }
    }

    std.testing.expect(found1 and found2 and !found3);
}

test "applyEventToState (add_shape)" {
    var state = State.init(std.testing.allocator);
    defer state.deinit();

    var event = parsing.Event{
        .add_shape = parsing.AddShapeData{
            .selector = parsing.Selector{ .groups = "grp" },
            .color = 123,
            .polygon = &[_]Vec3D{
                Vec3D{ .x = 1, .y = 2, .z = 3 },
                Vec3D{ .x = 4, .y = 5, .z = 6 },
                Vec3D{ .x = 7, .y = 8, .z = 9 },
            },
        },
    };

    try applyEventToState(&state, event);

    std.testing.expectEqual(@as(usize, 1), state.groups.items.len);

    const grp = &state.groups.items[0];
    std.testing.expectEqualStrings("grp", grp.name);
    std.testing.expectEqual(@as(usize, 1), grp.shapes.items.len);

    const shp = &grp.shapes.items[0];
    std.testing.expectEqual(@as(u8, 123), shp.attributes.color);
    std.testing.expectEqual(@as(usize, 0), shp.group);
    std.testing.expectEqualSlices(Vec3D, event.add_shape.polygon, shp.points);
    std.testing.expectEqual(Vec3D{ .x = 0, .y = 0, .z = 0 }, shp.velocity);
}

test "Update state with file" {
    var state = State.init(std.testing.allocator);
    defer state.deinit();

    var parser = parsing.Parser.init();

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
                try applyEventToState(&state, ev.event);
            },
        }
    }

    std.testing.expectEqual(@as(usize, 192), state.groups.items.len);
}

/// Tests if `group_name` matches the `pattern`.
/// Pattern may be either a full text or a prefix followed by `*`.
pub fn wildcardEquals(pattern: []const u8, group_name: []const u8) bool {
    if (isWildcardPattern(pattern)) {
        // wildcard match
        if (pattern.len - 1 > group_name.len)
            return false;
        const prefix_len = pattern.len - 1;
        return std.mem.eql(u8, pattern[0..prefix_len], group_name[0..prefix_len]);
    } else {
        // clean
        return std.mem.eql(u8, pattern, group_name);
    }
}

pub fn isWildcardPattern(pattern: []const u8) bool {
    return (pattern.len > 0) and (pattern[pattern.len - 1] == '*');
}

test "wildcardEquals empty match" {
    std.testing.expect(wildcardEquals("", ""));
}

test "wildcardEquals normal match" {
    std.testing.expect(wildcardEquals("foobar", "foobar"));
}

test "wildcardEquals normal mismatch" {
    std.testing.expect(wildcardEquals("barfoo", "foobar") == false);
}

test "wildcardEquals pattern too long" {
    std.testing.expect(wildcardEquals("pattern", "bar") == false);
}

test "wildcardEquals group_name too long" {
    std.testing.expect(wildcardEquals("pat", "foobar") == false);
}

test "wildcardEquals pattern wildcard exact match" {
    std.testing.expect(wildcardEquals("pat*", "pat"));
}

test "wildcardEquals pattern wildcard prefix match" {
    std.testing.expect(wildcardEquals("pat*", "pattern"));
}

test "wildcardEquals pattern wildcard prefix non-match" {
    std.testing.expect(wildcardEquals("pattern*", "pat") == false);
}
