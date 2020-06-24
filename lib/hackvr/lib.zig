const std = @import("std");

const real = f32;

pub const Vec3D = struct {
    x: real, y: real, z: real
};

pub const Attribute = struct {
    color: u8, //color. not sure how I plan on using this.
    luminance: u8, //brightness. 1 - 200 atm because X11 has grey1 - grey200
};

pub const Shape3D = struct {
    pub const Flavor = enum {
        polygon,
        elliptic_arc,
        cubic_bezier,
        quad_bezier,
    };

    id: []const u8,
    flavour: Flavor,
    points: []Vec3D,
    velocity: Vec3D,
    attributes: Attribute,
};
