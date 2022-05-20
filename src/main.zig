const std = @import("std");
const builtin = @import("builtin");

const zlm = @import("zlm");
const hackvr = @import("hackvr");
const gl = @import("zgl");
const zig_args = @import("zig-args");

const c = @cImport({
    @cInclude("SDL.h");
});

const SdlError = error{SdlFailure};

fn makeSdlError() SdlError {
    std.log.err("{s}", .{std.mem.sliceTo(c.SDL_GetError() orelse unreachable, 0)});
    return error.SdlFailure;
}

fn sdlCheck(result: c_int) !void {
    if (result < 0)
        return makeSdlError();
}

const Resolution = struct {
    const Self = @This();

    width: u16,
    height: u16,

    pub fn parse(str: []const u8) !Self {
        if (std.mem.indexOf(u8, str, "x")) |index| {
            return Self{
                .width = try std.fmt.parseInt(u16, str[0..index], 10),
                .height = try std.fmt.parseInt(u16, str[index + 1 ..], 10),
            };
        } else {
            return error.InvalidFormat;
        }
    }
};

const Color = extern struct {
    const Self = @This();

    pub const black = parse("#FFFFFF") catch unreachable;
    pub const white = parse("#FFFFFF") catch unreachable;
    pub const red = parse("#FF0000") catch unreachable;
    pub const green = parse("#00FF00") catch unreachable;
    pub const blue = parse("#0000FF") catch unreachable;
    pub const magenta = parse("#FF00FF") catch unreachable;
    pub const cyan = parse("#00FFFF") catch unreachable;
    pub const yellow = parse("#FF00FF") catch unreachable;

    red: f32,
    green: f32,
    blue: f32,
    alpha: f32 = 1.0,

    /// Supported formats:
    /// - `RGB`
    /// - `#RGB`
    /// - `RGBA`
    /// - `RRGGBB`
    /// - `#RRGGBB`
    /// - `RRGGBBAA`
    /// - `#RRGGBBAA`
    pub fn parse(col: []const u8) !Self {
        switch (col.len) {
            3 => {
                return Self{
                    .red = @intToFloat(f32, try std.fmt.parseInt(u8, col[0..1], 16)) / 15.0,
                    .green = @intToFloat(f32, try std.fmt.parseInt(u8, col[1..2], 16)) / 15.0,
                    .blue = @intToFloat(f32, try std.fmt.parseInt(u8, col[2..3], 16)) / 15.0,
                };
            },
            4 => {
                return if (col[0] == '#')
                    Self{
                        .red = @intToFloat(f32, try std.fmt.parseInt(u8, col[1..2], 16)) / 15.0,
                        .green = @intToFloat(f32, try std.fmt.parseInt(u8, col[2..3], 16)) / 15.0,
                        .blue = @intToFloat(f32, try std.fmt.parseInt(u8, col[3..4], 16)) / 15.0,
                    }
                else
                    Self{
                        .red = @intToFloat(f32, try std.fmt.parseInt(u8, col[0..1], 16)) / 15.0,
                        .green = @intToFloat(f32, try std.fmt.parseInt(u8, col[1..2], 16)) / 15.0,
                        .blue = @intToFloat(f32, try std.fmt.parseInt(u8, col[2..3], 16)) / 15.0,
                        .alpha = @intToFloat(f32, try std.fmt.parseInt(u8, col[3..4], 16)) / 15.0,
                    };
            },
            5 => {
                if (col[0] != '#')
                    return error.InvalidFormat;
                return Self{
                    .red = @intToFloat(f32, try std.fmt.parseInt(u8, col[1..2], 16)) / 15.0,
                    .green = @intToFloat(f32, try std.fmt.parseInt(u8, col[2..3], 16)) / 15.0,
                    .blue = @intToFloat(f32, try std.fmt.parseInt(u8, col[3..4], 16)) / 15.0,
                    .alpha = @intToFloat(f32, try std.fmt.parseInt(u8, col[4..5], 16)) / 15.0,
                };
            },
            6 => {
                return Self{
                    .red = @intToFloat(f32, try std.fmt.parseInt(u8, col[0..2], 16)) / 255.0,
                    .green = @intToFloat(f32, try std.fmt.parseInt(u8, col[2..4], 16)) / 255.0,
                    .blue = @intToFloat(f32, try std.fmt.parseInt(u8, col[4..6], 16)) / 255.0,
                };
            },
            7 => {
                if (col[0] != '#')
                    return error.InvalidFormat;
                return Self{
                    .red = @intToFloat(f32, try std.fmt.parseInt(u8, col[1..3], 16)) / 255.0,
                    .green = @intToFloat(f32, try std.fmt.parseInt(u8, col[3..5], 16)) / 255.0,
                    .blue = @intToFloat(f32, try std.fmt.parseInt(u8, col[5..7], 16)) / 255.0,
                };
            },
            8 => {
                return Self{
                    .red = @intToFloat(f32, try std.fmt.parseInt(u8, col[0..2], 16)) / 255.0,
                    .green = @intToFloat(f32, try std.fmt.parseInt(u8, col[2..4], 16)) / 255.0,
                    .blue = @intToFloat(f32, try std.fmt.parseInt(u8, col[4..6], 16)) / 255.0,
                    .alpha = @intToFloat(f32, try std.fmt.parseInt(u8, col[6..8], 16)) / 255.0,
                };
            },
            9 => {
                if (col[0] != '#')
                    return error.InvalidFormat;
                return Self{
                    .red = @intToFloat(f32, try std.fmt.parseInt(u8, col[1..3], 16)) / 255.0,
                    .green = @intToFloat(f32, try std.fmt.parseInt(u8, col[3..5], 16)) / 255.0,
                    .blue = @intToFloat(f32, try std.fmt.parseInt(u8, col[5..7], 16)) / 255.0,
                    .alpha = @intToFloat(f32, try std.fmt.parseInt(u8, col[7..9], 16)) / 255.0,
                };
            },
            else => return error.InvalidFormat,
        }
    }
};

const CliOptions = struct {
    resolution: Resolution = Resolution{
        .width = 1280,
        .height = 720,
    },
    fullscreen: bool = false,
    multisampling: ?u7 = null,
    background: Color = Color.parse("#000020") catch unreachable,

    pub const shorthands = .{
        .f = "fullscreen",
        .r = "resolution",
        .m = "multisampling",
        .b = "background",
    };
};

// https://lospec.com/palette-list/dawnbringer-16
const palette = [_]Color{
    Color.parse("#140c1c") catch unreachable,
    Color.parse("#442434") catch unreachable,
    Color.parse("#30346d") catch unreachable,
    Color.parse("#4e4a4e") catch unreachable,
    Color.parse("#854c30") catch unreachable,
    Color.parse("#346524") catch unreachable,
    Color.parse("#d04648") catch unreachable,
    Color.parse("#757161") catch unreachable,
    Color.parse("#597dce") catch unreachable,
    Color.parse("#d27d2c") catch unreachable,
    Color.parse("#8595a1") catch unreachable,
    Color.parse("#6daa2c") catch unreachable,
    Color.parse("#d2aa99") catch unreachable,
    Color.parse("#6dc2ca") catch unreachable,
    Color.parse("#dad45e") catch unreachable,
    Color.parse("#deeed6") catch unreachable,
};

const Vertex = extern struct {
    position: zlm.Vec3,
    color: Color,
};

fn getGroupTransform(state: hackvr.State, group: hackvr.Group) zlm.Mat4 {
    var transform = zlm.Mat4.batchMul(&[_]zlm.Mat4{
        zlm.Mat4.createAngleAxis(zlm.Vec3.unitZ, zlm.toRadians(group.rotation.z)),
        zlm.Mat4.createAngleAxis(zlm.Vec3.unitX, zlm.toRadians(group.rotation.x)),
        zlm.Mat4.createAngleAxis(zlm.Vec3.unitY, zlm.toRadians(group.rotation.y)),
        zlm.Mat4.createTranslation(group.translation),
    });

    if (group.parent) |parent| {
        var parent_transform = getGroupTransform(state, state.groups.items[parent]);

        return transform.mul(parent_transform);
    } else {
        return transform;
    }
}

pub fn main() !u8 {
    var gpa_backing = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa_backing.deinit();
    const gpa = gpa_backing.allocator();

    var cli = zig_args.parseForCurrentProcess(CliOptions, gpa, .print) catch return 1;
    defer cli.deinit();

    if (c.SDL_Init(c.SDL_INIT_EVERYTHING) < 0) {
        return makeSdlError();
    }
    defer _ = c.SDL_Quit();

    try sdlCheck(c.SDL_GL_SetAttribute(c.SDL_GL_CONTEXT_MAJOR_VERSION, 3));
    try sdlCheck(c.SDL_GL_SetAttribute(c.SDL_GL_CONTEXT_MINOR_VERSION, 3));
    try sdlCheck(c.SDL_GL_SetAttribute(c.SDL_GL_CONTEXT_FLAGS, c.SDL_GL_CONTEXT_FORWARD_COMPATIBLE_FLAG | c.SDL_GL_CONTEXT_DEBUG_FLAG));

    if (cli.options.multisampling) |samples| {
        try sdlCheck(c.SDL_GL_SetAttribute(c.SDL_GL_MULTISAMPLEBUFFERS, 1));
        try sdlCheck(c.SDL_GL_SetAttribute(c.SDL_GL_MULTISAMPLESAMPLES, samples));
    }

    var window = c.SDL_CreateWindow(
        "HackVR Turbo",
        c.SDL_WINDOWPOS_CENTERED,
        c.SDL_WINDOWPOS_CENTERED,
        @intCast(c_int, cli.options.resolution.width),
        @intCast(c_int, cli.options.resolution.height),
        @intCast(u32, c.SDL_WINDOW_OPENGL | (if (cli.options.fullscreen) c.SDL_WINDOW_FULLSCREEN_DESKTOP else 0)),
    ) orelse return makeSdlError();
    defer c.SDL_DestroyWindow(window);

    var context = c.SDL_GL_CreateContext(window) orelse return makeSdlError();
    defer _ = c.SDL_GL_DeleteContext(context);

    try sdlCheck(c.SDL_GL_MakeCurrent(window, context));

    gl.debugMessageCallback({}, openGlDebugCallback);

    var state = hackvr.State.init(gpa);
    defer state.deinit();

    var vao = gl.createVertexArray();
    defer vao.delete();

    vao.enableVertexAttribute(0);
    vao.enableVertexAttribute(1);

    vao.attribFormat(
        0,
        3,
        .float,
        false,
        @offsetOf(Vertex, "position"),
    );
    vao.attribFormat(
        1,
        4,
        .float,
        false,
        @offsetOf(Vertex, "color"),
    );

    vao.attribBinding(0, 0);
    vao.attribBinding(1, 0);

    var tris_vertex_buffer = gl.createBuffer();
    defer tris_vertex_buffer.delete();

    var lines_vertex_buffer = gl.createBuffer();
    defer lines_vertex_buffer.delete();

    var point_vertex_buffer = gl.createBuffer();
    defer point_vertex_buffer.delete();

    const PolygonGroup = struct {
        group_index: usize,
        transform: zlm.Mat4,
        begin_tris: usize,
        count_tris: usize,
        begin_lines: usize,
        count_lines: usize,
    };

    var poly_groups = std.ArrayList(PolygonGroup).init(gpa);
    defer poly_groups.deinit();

    var vertex_list = std.ArrayList(Vertex).init(gpa);
    defer vertex_list.deinit();

    var point_list = std.ArrayList(Vertex).init(gpa);
    defer point_list.deinit();

    var outline_list = std.ArrayList(Vertex).init(gpa);
    defer outline_list.deinit();

    var shader_program = gl.createProgram();
    defer shader_program.delete();

    {
        var vertex_shader = gl.createShader(.vertex);
        defer vertex_shader.delete();

        var fragment_shader = gl.createShader(.fragment);
        defer fragment_shader.delete();

        vertex_shader.source(1, &[_][]const u8{
            @embedFile("./shader/flat.vert"),
        });

        fragment_shader.source(1, &[_][]const u8{
            @embedFile("./shader/flat.frag"),
        });

        vertex_shader.compile();
        if (vertex_shader.get(.compile_status) == 0) {
            const compile_log = try vertex_shader.getCompileLog(gpa);
            defer gpa.free(compile_log);

            std.debug.print("failed to compile vertex shader:\n{s}", .{compile_log});
            return 1;
        }

        fragment_shader.compile();
        if (fragment_shader.get(.compile_status) == 0) {
            const compile_log = try fragment_shader.getCompileLog(gpa);
            defer gpa.free(compile_log);

            std.debug.print("failed to compile fragment shader:\n{s}", .{compile_log});
            return 1;
        }

        shader_program.attach(vertex_shader);
        defer shader_program.detach(vertex_shader);

        shader_program.attach(fragment_shader);
        defer shader_program.detach(fragment_shader);

        shader_program.link();
        if (shader_program.get(.link_status) == 0) {
            const link_log = try shader_program.getCompileLog(gpa);
            defer gpa.free(link_log);

            std.log.err("failed to compile fragment shader:\n{s}", .{link_log});
            return 1;
        }
    }

    const transform_loc = shader_program.uniformLocation("uTransform") orelse {
        std.log.err("Failed to query uniform uTransform!", .{});
        return 1;
    };

    const highlighted_loc = shader_program.uniformLocation("uHighlighting") orelse {
        std.log.err("Failed to query uniform uHighlighting!", .{});
        return 1;
    };

    gl.enable(.depth_test);
    gl.depthFunc(.less_or_equal);
    gl.pointSize(5.0);

    var time: f32 = 0.0;

    var hackvr_dirty = true;

    var parser = hackvr.parsing.Parser.init();

    const stdin = std.io.getStdIn().reader();
    const stderr = std.io.getStdErr().writer();
    const stdout = std.io.getStdOut().writer();

    _ = try std.os.fcntl(
        std.io.getStdIn().handle,
        std.os.F.SETFL,
        std.os.O.NONBLOCK | try std.os.fcntl(std.io.getStdIn().handle, std.os.F.GETFL, 0),
    );

    const user_name = try std.process.getEnvVarOwned(gpa, "USER");
    defer gpa.free(user_name);

    var camera = try state.getOrCreateGroup(user_name);
    camera.translation = zlm.Vec3.zero;
    camera.rotation = zlm.Vec3{
        .x = 0,
        .y = zlm.toRadians(-180.0),
        .z = 0,
    };

    const dt = 1.0 / 60.0;

    mainLoop: while (true) : (time += dt) {
        point_list.shrinkRetainingCapacity(0);

        // process HackVR events
        if (try isDataOnStdInAvailable()) {
            var buffer: [256]u8 = undefined;

            while (true) {
                const len = stdin.read(&buffer) catch |err| switch (err) {
                    error.WouldBlock => break,
                    else => |e| return e,
                };
                if (len == 0) // EOF
                    break;

                var slice: []const u8 = buffer[0..len];

                while (slice.len > 0) {
                    var item = try parser.push(slice);
                    switch (item) {
                        // should never be reached as the test.hackvr is a complete file, terminated by a LF
                        .needs_data => {
                            // just happily accept that the data wasn't enough
                            break;
                        },

                        // should never be reached as the test.hackvr file is correct
                        .parse_error => |err| {
                            try stdout.print("# Error while parsing line: {}\n# '{s}'\n", .{
                                err.error_type,
                                err.source,
                            });
                            try stderr.print("# Error while parsing line: {}\n# '{s}'\n", .{
                                err.error_type,
                                err.source,
                            });
                            slice = err.rest;
                        },

                        .event => |ev| {
                            slice = ev.rest;
                            switch (ev.event) {
                                .set => |cmd| {
                                    if (std.mem.eql(u8, cmd.key, "camera.p.x")) {
                                        camera.translation.x = std.fmt.parseFloat(f32, cmd.value) catch camera.translation.x;
                                    } else if (std.mem.eql(u8, cmd.key, "camera.p.y")) {
                                        camera.translation.y = std.fmt.parseFloat(f32, cmd.value) catch camera.translation.y;
                                    } else if (std.mem.eql(u8, cmd.key, "camera.p.z")) {
                                        camera.translation.z = std.fmt.parseFloat(f32, cmd.value) catch camera.translation.z;
                                    } else {
                                        std.debug.print("unknown key for command set: {s} {s}\n", .{
                                            cmd.key,
                                            cmd.value,
                                        });
                                    }
                                },
                                else => try hackvr.applyEventToState(&state, ev.event),
                            }
                            hackvr_dirty = true;

                            //  we need to update the camera pointer as it may have changed
                            camera = try state.getOrCreateGroup(user_name);
                        },
                    }
                }
            }
        }

        var signal_picked_shape = false;

        // process SDL events
        {
            var event: c.SDL_Event = undefined;
            while (c.SDL_PollEvent(&event) != 0) {
                switch (event.type) {
                    c.SDL_QUIT => break :mainLoop,
                    c.SDL_MOUSEBUTTONDOWN => {
                        if (event.button.button == c.SDL_BUTTON_LEFT) {
                            signal_picked_shape = true;
                        }
                    },
                    c.SDL_MOUSEMOTION => {
                        const motion = &event.motion;

                        if ((motion.state & 4) != 0) {
                            camera.rotation.y -= @intToFloat(f32, motion.xrel) / 150.0;
                            camera.rotation.x -= @intToFloat(f32, motion.yrel) / 150.0;
                        }
                    },
                    else => {
                        // std.log.notice(.HackVR, "Unhandled event: {}\n", .{event.type});
                    },
                }
            }

            const movespeed = 7.5;
            const turnspeed = 2.0;

            const keys = c.SDL_GetKeyboardState(null);

            var move_dir = zlm.Vec3.zero;

            if ((keys[c.SDL_SCANCODE_UP] != 0) or (keys[c.SDL_SCANCODE_W] != 0)) {
                move_dir.z -= 1;
            }
            if ((keys[c.SDL_SCANCODE_DOWN] != 0) or (keys[c.SDL_SCANCODE_S] != 0)) {
                move_dir.z += 1;
            }

            if (keys[c.SDL_SCANCODE_D] != 0) {
                move_dir.x -= 1;
            }
            if (keys[c.SDL_SCANCODE_A] != 0) {
                move_dir.x += 1;
            }

            if (keys[c.SDL_SCANCODE_LALT] != 0) {
                // Strafing
                if (keys[c.SDL_SCANCODE_RIGHT] != 0) {
                    move_dir.x -= 1;
                }
                if (keys[c.SDL_SCANCODE_LEFT] != 0) {
                    move_dir.x += 1;
                }
            } else {
                // Turning
                if (keys[c.SDL_SCANCODE_RIGHT] != 0) {
                    camera.rotation.y -= turnspeed * dt;
                }
                if (keys[c.SDL_SCANCODE_LEFT] != 0) {
                    camera.rotation.y += turnspeed * dt;
                }
            }

            if (keys[c.SDL_SCANCODE_LALT] != 0) {
                if (keys[c.SDL_SCANCODE_PAGEUP] != 0) {
                    move_dir.y += 1;
                }
                if (keys[c.SDL_SCANCODE_PAGEDOWN] != 0) {
                    move_dir.y -= 1;
                }
            } else {
                // Tilting
                if (keys[c.SDL_SCANCODE_PAGEUP] != 0) {
                    camera.rotation.x += turnspeed * dt;
                }
                if (keys[c.SDL_SCANCODE_PAGEDOWN] != 0) {
                    camera.rotation.x -= turnspeed * dt;
                }
            }

            const pan_rot = zlm.Mat4.createAngleAxis(zlm.Vec3.unitY, camera.rotation.y);
            const tilt_rot = zlm.Mat4.createAngleAxis(zlm.Vec3.unitX.scale(-1), camera.rotation.x);

            move_dir = move_dir.transformDirection(tilt_rot.mul(pan_rot));

            camera.translation = camera.translation.add(move_dir.scale(movespeed * dt));
        }

        // Render scene from HackVR dataset
        if (hackvr_dirty or true) {
            hackvr_dirty = false;

            vertex_list.shrinkRetainingCapacity(0);
            poly_groups.shrinkRetainingCapacity(0);

            var group_index: usize = 0;
            var groups = state.iterator();
            while (groups.next()) |group| : (group_index += 1) {
                var poly_grp = PolygonGroup{
                    .group_index = group_index,
                    .begin_tris = vertex_list.items.len,
                    .count_tris = undefined,
                    .begin_lines = outline_list.items.len,
                    .count_lines = undefined,

                    .transform = getGroupTransform(state, group.*),
                };

                for (group.shapes.items) |*shape| {
                    if (shape.points.len == 0) {
                        // wat?
                    } else if (shape.points.len == 1) {
                        try point_list.append(Vertex{
                            .position = shape.points[0],
                            .color = palette[shape.attributes.color % 16],
                        });
                    } else if (shape.points.len == 2) {
                        try outline_list.append(Vertex{
                            .position = shape.points[0],
                            .color = palette[shape.attributes.color % 16],
                        });
                        try outline_list.append(Vertex{
                            .position = shape.points[1],
                            .color = palette[shape.attributes.color % 16],
                        });
                    } else {
                        // Simple fan-out triangulation.
                        // Not beautiful, but very simple
                        var i: usize = 2;
                        while (i < shape.points.len) {
                            try vertex_list.append(Vertex{
                                .position = shape.points[0],
                                .color = palette[shape.attributes.color % 16],
                            });
                            try vertex_list.append(Vertex{
                                .position = shape.points[i - 1],
                                .color = palette[shape.attributes.color % 16],
                            });
                            try vertex_list.append(Vertex{
                                .position = shape.points[i],
                                .color = palette[shape.attributes.color % 16],
                            });

                            i += 1;
                        }

                        i = 1;
                        while (i < shape.points.len) {
                            try outline_list.append(Vertex{
                                .position = shape.points[i - 1],
                                .color = Color.white,
                            });
                            try outline_list.append(Vertex{
                                .position = shape.points[i],
                                .color = Color.white,
                            });
                            i += 1;
                        }
                        try outline_list.append(Vertex{
                            .position = shape.points[0],
                            .color = Color.white,
                        });
                        try outline_list.append(Vertex{
                            .position = shape.points[shape.points.len - 1],
                            .color = Color.white,
                        });
                    }
                }
                poly_grp.count_tris = vertex_list.items.len - poly_grp.begin_tris;
                poly_grp.count_lines = outline_list.items.len - poly_grp.begin_lines;

                try poly_groups.append(poly_grp);
            }
        }

        const mat_proj = zlm.Mat4.createPerspective(1.0, 16.0 / 9.0, 0.1, 10000.0);
        const mat_view = zlm.Mat4.createLook(
            camera.translation,
            zlm.Vec3{
                .x = std.math.sin(camera.rotation.y) * std.math.cos(camera.rotation.x),
                .y = std.math.sin(camera.rotation.x),
                .z = -std.math.cos(camera.rotation.y) * std.math.cos(camera.rotation.x),
            },
            zlm.Vec3.unitY,
        );

        const mat_view_proj = mat_view.mul(mat_proj);

        const mat_view_proj_inv = invertMatrix(mat_view_proj) orelse unreachable;

        // std.debug.warn("normal: {}\n", .{mat_view_proj});
        // std.debug.warn("invert: {}\n", .{mat_view_proj_inv});

        const PickedShape = struct {
            group_index: usize,
            shape_index: usize,
            group: *hackvr.Group,
            shape: *hackvr.Shape3D,
        };

        var picked_shape: ?PickedShape = blk: {
            var window_w: c_int = undefined;
            var window_h: c_int = undefined;
            c.SDL_GetWindowSize(window, &window_w, &window_h);

            var mouse_x: c_int = undefined;
            var mouse_y: c_int = undefined;
            _ = c.SDL_GetMouseState(&mouse_x, &mouse_y);

            // var f = try std.fs.cwd().createFile("debug.pgm", .{ .truncate = true });
            // defer f.close();

            // try f.writeAll("P5 1280 720 255\n");

            // var f = try std.fs.cwd().createFile("debug.stl", .{ .truncate = true });
            // defer f.close();

            // try f.writeAll(&@as([80]u8, undefined));

            // try f.writeAll("\x00\x00\x00\x00");
            // var cnt: usize = 0;

            // mouse_y = 0;
            // while (mouse_y < 720) : (mouse_y += 1) {
            //     mouse_x = 0;
            //     while (mouse_x < 1280) : (mouse_x += 1) {
            var mouse_pos_near_ss = zlm.Vec4{
                .x = 2.0 * @intToFloat(f32, mouse_x) / @intToFloat(f32, window_w - 1) - 1.0,
                .y = 1.0 - 2.0 * @intToFloat(f32, mouse_y) / @intToFloat(f32, window_h - 1),
                .z = 0.0,
                .w = 1.0,
            };
            var mouse_pos_far_ss = zlm.Vec4{
                .x = mouse_pos_near_ss.x,
                .y = mouse_pos_near_ss.y,
                .z = 1.0,
                .w = 1.0,
            };

            // std.debug.print("ss {} {}\n", .{ mouse_pos_near_ss, mouse_pos_far_ss });

            var mouse_pos_near_ws = mouse_pos_near_ss.transform(mat_view_proj_inv);
            mouse_pos_near_ws = mouse_pos_near_ws.scale(1.0 / mouse_pos_near_ws.w);

            var mouse_pos_far_ws = mouse_pos_far_ss.transform(mat_view_proj_inv);
            mouse_pos_far_ws = mouse_pos_far_ws.scale(1.0 / mouse_pos_far_ws.w);

            // std.debug.print("ws {} {}\n", .{ mouse_pos_near_ws, mouse_pos_far_ws });

            const Buffer = struct {
                var orig: zlm.Vec3 = undefined;
                var dir: zlm.Vec3 = undefined;
            };

            //if (c.SDL_GetKeyboardState(null)[c.SDL_SCANCODE_SPACE] != 0) {
            Buffer.orig = mouse_pos_near_ws.swizzle("xyz");
            Buffer.dir = mouse_pos_far_ws.swizzle("xyz").sub(Buffer.orig).normalize();
            //}
            if (c.SDL_GetKeyboardState(null)[c.SDL_SCANCODE_V] != 0) {
                Buffer.dir = Buffer.dir.transformDirection(zlm.Mat4.createAngleAxis(zlm.Vec3.unitY, dt));
            }

            var ray_origin = Buffer.orig;
            var ray_direction = Buffer.dir;

            // var ray_origin = mouse_pos_near_ws.swizzle("xyz");

            // var ray_direction = mouse_pos_far_ws.swizzle("xyz").sub(ray_origin).normalize();

            var distance = std.math.inf(f32);

            var result: ?PickedShape = null;

            var group_index: usize = 0;
            var groups = state.iterator();
            while (groups.next()) |group| : (group_index += 1) {
                const transform = getGroupTransform(state, group.*);

                for (group.shapes.items) |*shape, shape_index| {
                    if (shape.points.len < 3) {
                        // we can't pick lines or points
                    } else {
                        // Simple fan-out triangulation.
                        // Not beautiful, but very simple
                        const pivot = shape.points[0].transformPosition(transform);

                        var chain_point = shape.points[1].transformPosition(transform);

                        var i: usize = 2;
                        while (i < shape.points.len) {
                            const point = shape.points[i].transformPosition(transform);

                            // try f.writeAll(&@bitCast([12]u8, zlm.Vec3{ .x = 0, .y = 0, .z = 0 }));
                            // try f.writeAll(&@bitCast([12]u8, pivot));
                            // try f.writeAll(&@bitCast([12]u8, chain_point));
                            // try f.writeAll(&@bitCast([12]u8, point));
                            // try f.writeAll("\x00\x00");
                            // cnt += 1;

                            if (rayTriangleIntersect(
                                ray_origin,
                                ray_direction,
                                pivot,
                                chain_point,
                                point,
                            )) |dist| {
                                if (dist < distance) {
                                    distance = dist;
                                    result = PickedShape{
                                        .group_index = group_index,
                                        .shape_index = shape_index,
                                        .shape = shape,
                                        .group = group,
                                    };
                                }
                            }
                            chain_point = point;

                            i += 1;
                        }
                        i = 0;

                        // while (i < shape.points.len) {
                        //     try point_list.append(Vertex{
                        //         .position = shape.points[i].transformPosition(transform),
                        //         .color = parseColor("#FF0000"),
                        //     });
                        //     i += 1;
                        // }
                    }
                }
            }

            // try f.seekTo(80);
            // try f.writeAll(&@bitCast([4]u8, @intCast(u32, cnt)));

            // try f.writeAll(if (result != null) "\xFF" else "\x00");
            //     }
            // }

            // break :blk null;

            // {
            //     var step: usize = 0;
            //     var dist: f32 = 0.0;
            //     var pos = ray_origin;
            //     while (step < 250) : (step += 1) {
            //         try point_list.append(Vertex{
            //             .position = pos,
            //             .color = if (dist < distance) parseColor("#FFFF00") else parseColor("#0000FF"),
            //         });
            //         pos = pos.add(ray_direction.scale(0.25));
            //         dist += 0.25;
            //     }
            // }

            // const size = 0.1;

            // if (result != null) {
            //     try point_list.append(Vertex{
            //         .position = ray_origin.add(ray_direction.scale(distance)).sub(zlm.Vec3.unitX.scale(size)),
            //         .color = parseColor("#FF00FF"),
            //     });
            //     try point_list.append(Vertex{
            //         .position = ray_origin.add(ray_direction.scale(distance)).add(zlm.Vec3.unitX.scale(size)),
            //         .color = parseColor("#FF00FF"),
            //     });
            //     try point_list.append(Vertex{
            //         .position = ray_origin.add(ray_direction.scale(distance)).sub(zlm.Vec3.unitY.scale(size)),
            //         .color = parseColor("#FF00FF"),
            //     });
            //     try point_list.append(Vertex{
            //         .position = ray_origin.add(ray_direction.scale(distance)).add(zlm.Vec3.unitY.scale(size)),
            //         .color = parseColor("#FF00FF"),
            //     });
            //     try point_list.append(Vertex{
            //         .position = ray_origin.add(ray_direction.scale(distance)).sub(zlm.Vec3.unitZ.scale(size)),
            //         .color = parseColor("#FF00FF"),
            //     });
            //     try point_list.append(Vertex{
            //         .position = ray_origin.add(ray_direction.scale(distance)).add(zlm.Vec3.unitZ.scale(size)),
            //         .color = parseColor("#FF00FF"),
            //     });
            // }

            break :blk result;
        };

        if (signal_picked_shape) {
            if (picked_shape) |indices| {
                try stdout.print("{s} action {s}\n", .{
                    "USER",
                    indices.group.name,
                });
            }
        }

        gl.namedBufferData(tris_vertex_buffer, Vertex, vertex_list.items, .dynamic_draw);
        gl.namedBufferData(lines_vertex_buffer, Vertex, outline_list.items, .dynamic_draw);
        gl.namedBufferData(point_vertex_buffer, Vertex, point_list.items, .dynamic_draw);

        // render graphics
        {
            gl.clearColor(
                cli.options.background.red,
                cli.options.background.green,
                cli.options.background.blue,
                1.0,
            );
            gl.clearDepth(1.0);
            gl.clear(.{
                .color = true,
                .depth = true,
            });

            vao.bind();
            shader_program.use();

            gl.programUniform1f(
                shader_program,
                highlighted_loc,
                0.0,
            );

            vao.vertexBuffer(0, tris_vertex_buffer, 0, @sizeOf(Vertex));
            for (poly_groups.items) |poly_grp| {
                const transform = zlm.Mat4.mul(poly_grp.transform, mat_view_proj);

                gl.programUniformMatrix4(
                    shader_program,
                    transform_loc,
                    false,
                    @ptrCast([*]const [4][4]f32, &transform.fields)[0..1],
                );

                gl.drawArrays(.triangles, poly_grp.begin_tris, poly_grp.count_tris);
            }

            gl.enable(.polygon_offset_line);
            gl.polygonOffset(0.0, -16.0);

            vao.vertexBuffer(0, lines_vertex_buffer, 0, @sizeOf(Vertex));
            for (poly_groups.items) |poly_grp| {
                const transform = zlm.Mat4.mul(poly_grp.transform, mat_view_proj);

                const picked = if (picked_shape) |indices|
                    indices.group_index == poly_grp.group_index
                else
                    false;

                gl.programUniform1f(
                    shader_program,
                    highlighted_loc,
                    if (picked) @as(f32, 1.0) else @as(f32, 0.0),
                );

                gl.programUniformMatrix4(
                    shader_program,
                    transform_loc,
                    false,
                    @ptrCast([*]const [4][4]f32, &transform.fields)[0..1],
                );
                gl.drawArrays(.lines, poly_grp.begin_lines, poly_grp.count_lines);
            }

            vao.vertexBuffer(0, point_vertex_buffer, 0, @sizeOf(Vertex));
            {
                var transform = mat_view_proj;
                gl.programUniformMatrix4(
                    shader_program,
                    transform_loc,
                    false,
                    @ptrCast([*]const [4][4]f32, &transform.fields)[0..1],
                );
                gl.drawArrays(.points, 0, point_list.items.len);
            }

            c.SDL_GL_SwapWindow(window);
            c.SDL_Delay(10);
        }
    }
    return 0;
}

fn openGlDebugCallback(
    source: gl.DebugSource,
    msg_type: gl.DebugMessageType,
    id: usize,
    severity: gl.DebugSeverity,
    message: []const u8,
) void {
    _ = id;
    const msg_fmt = "[{s}/{s}] {s}";
    const msg_arg = .{ @tagName(source), @tagName(msg_type), message };

    switch (severity) {
        .high => std.log.err(msg_fmt, msg_arg),
        .medium => std.log.warn(msg_fmt, msg_arg),
        .low => std.log.warn(msg_fmt, msg_arg),
        .notification => std.log.info(msg_fmt, msg_arg),
    }
}

fn isDataOnStdInAvailable() !bool {
    const stdin = std.io.getStdIn();
    if (builtin.os.tag == .linux) {
        var fds = [1]std.os.pollfd{
            .{
                .fd = stdin.handle,
                .events = std.os.POLL.IN,
                .revents = 0,
            },
        };
        _ = try std.os.poll(&fds, 0);
        if ((fds[0].revents & std.os.POLL.IN) != 0) {
            return true;
        }
    }
    if (builtin.os.tag == .windows) {
        std.os.windows.WaitForSingleObject(stdin.handle, 0) catch |err| switch (err) {
            error.WaitTimeOut => return false,
            else => return err,
        };
        return true;
    }
    return false;
}

fn rayTriangleIntersect(ro: zlm.Vec3, rd: zlm.Vec3, v0: zlm.Vec3, v1: zlm.Vec3, v2: zlm.Vec3) ?f32 {
    const v1v0 = v1.sub(v0);
    const v2v0 = v2.sub(v0);
    const rov0 = ro.sub(v0);
    const n = zlm.Vec3.cross(v1v0, v2v0);
    const q = zlm.Vec3.cross(rov0, rd);
    const d = 1.0 / zlm.Vec3.dot(rd, n);
    const u = d * zlm.Vec3.dot(q.scale(-1), v2v0);
    const v = d * zlm.Vec3.dot(q, v1v0);
    const t = d * zlm.Vec3.dot(n.scale(-1), rov0);
    if (t < 0) {
        return null;
    }
    if (u < 0.0 or u > 1.0 or v < 0.0 or (u + v) > 1.0) {
        //  t = -1.0;
        return null;
    }
    return t;
    // return vec3( t, u, v );
}

fn invertMatrix(mat: zlm.Mat4) ?zlm.Mat4 {
    const m = @bitCast([16]f32, mat.fields);
    var inv: [16]f32 = undefined;

    inv[0] = m[5] * m[10] * m[15] -
        m[5] * m[11] * m[14] -
        m[9] * m[6] * m[15] +
        m[9] * m[7] * m[14] +
        m[13] * m[6] * m[11] -
        m[13] * m[7] * m[10];

    inv[4] = -m[4] * m[10] * m[15] +
        m[4] * m[11] * m[14] +
        m[8] * m[6] * m[15] -
        m[8] * m[7] * m[14] -
        m[12] * m[6] * m[11] +
        m[12] * m[7] * m[10];

    inv[8] = m[4] * m[9] * m[15] -
        m[4] * m[11] * m[13] -
        m[8] * m[5] * m[15] +
        m[8] * m[7] * m[13] +
        m[12] * m[5] * m[11] -
        m[12] * m[7] * m[9];

    inv[12] = -m[4] * m[9] * m[14] +
        m[4] * m[10] * m[13] +
        m[8] * m[5] * m[14] -
        m[8] * m[6] * m[13] -
        m[12] * m[5] * m[10] +
        m[12] * m[6] * m[9];

    inv[1] = -m[1] * m[10] * m[15] +
        m[1] * m[11] * m[14] +
        m[9] * m[2] * m[15] -
        m[9] * m[3] * m[14] -
        m[13] * m[2] * m[11] +
        m[13] * m[3] * m[10];

    inv[5] = m[0] * m[10] * m[15] -
        m[0] * m[11] * m[14] -
        m[8] * m[2] * m[15] +
        m[8] * m[3] * m[14] +
        m[12] * m[2] * m[11] -
        m[12] * m[3] * m[10];

    inv[9] = -m[0] * m[9] * m[15] +
        m[0] * m[11] * m[13] +
        m[8] * m[1] * m[15] -
        m[8] * m[3] * m[13] -
        m[12] * m[1] * m[11] +
        m[12] * m[3] * m[9];

    inv[13] = m[0] * m[9] * m[14] -
        m[0] * m[10] * m[13] -
        m[8] * m[1] * m[14] +
        m[8] * m[2] * m[13] +
        m[12] * m[1] * m[10] -
        m[12] * m[2] * m[9];

    inv[2] = m[1] * m[6] * m[15] -
        m[1] * m[7] * m[14] -
        m[5] * m[2] * m[15] +
        m[5] * m[3] * m[14] +
        m[13] * m[2] * m[7] -
        m[13] * m[3] * m[6];

    inv[6] = -m[0] * m[6] * m[15] +
        m[0] * m[7] * m[14] +
        m[4] * m[2] * m[15] -
        m[4] * m[3] * m[14] -
        m[12] * m[2] * m[7] +
        m[12] * m[3] * m[6];

    inv[10] = m[0] * m[5] * m[15] -
        m[0] * m[7] * m[13] -
        m[4] * m[1] * m[15] +
        m[4] * m[3] * m[13] +
        m[12] * m[1] * m[7] -
        m[12] * m[3] * m[5];

    inv[14] = -m[0] * m[5] * m[14] +
        m[0] * m[6] * m[13] +
        m[4] * m[1] * m[14] -
        m[4] * m[2] * m[13] -
        m[12] * m[1] * m[6] +
        m[12] * m[2] * m[5];

    inv[3] = -m[1] * m[6] * m[11] +
        m[1] * m[7] * m[10] +
        m[5] * m[2] * m[11] -
        m[5] * m[3] * m[10] -
        m[9] * m[2] * m[7] +
        m[9] * m[3] * m[6];

    inv[7] = m[0] * m[6] * m[11] -
        m[0] * m[7] * m[10] -
        m[4] * m[2] * m[11] +
        m[4] * m[3] * m[10] +
        m[8] * m[2] * m[7] -
        m[8] * m[3] * m[6];

    inv[11] = -m[0] * m[5] * m[11] +
        m[0] * m[7] * m[9] +
        m[4] * m[1] * m[11] -
        m[4] * m[3] * m[9] -
        m[8] * m[1] * m[7] +
        m[8] * m[3] * m[5];

    inv[15] = m[0] * m[5] * m[10] -
        m[0] * m[6] * m[9] -
        m[4] * m[1] * m[10] +
        m[4] * m[2] * m[9] +
        m[8] * m[1] * m[6] -
        m[8] * m[2] * m[5];

    const det = m[0] * inv[0] + m[1] * inv[4] + m[2] * inv[8] + m[3] * inv[12];

    if (det == 0)
        return null;

    const inv_det = 1.0 / det;

    for (inv) |*val| {
        val.* *= inv_det;
    }

    return zlm.Mat4{
        .fields = @bitCast([4][4]f32, inv),
    };
}
