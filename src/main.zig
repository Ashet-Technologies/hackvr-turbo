const std = @import("std");

const zlm = @import("zlm");
const hackvr = @import("hackvr");
const gl = @import("zgl");

const c = @cImport({
    @cInclude("SDL.h");
});

const SdlError = error{SdlFailure};

fn makeSdlError() SdlError {
    std.log.err(.SDL, "{c}\n", .{c.SDL_GetError()});
    return error.SdlFailure;
}

fn sdlCheck(result: c_int) !void {
    if (result < 0)
        return makeSdlError();
}

const CliOptions = struct {
    multisampling: ?u7 = null,
};

const cli_options = CliOptions{
    .multisampling = 8,
};

fn parseColor(comptime col: []const u8) zlm.Vec3 {
    std.debug.assert(col.len == 7);
    std.debug.assert(col[0] == '#');
    return zlm.Vec3{
        .x = @intToFloat(f32, std.fmt.parseInt(u8, col[1..3], 16) catch unreachable) / 255.0,
        .y = @intToFloat(f32, std.fmt.parseInt(u8, col[3..5], 16) catch unreachable) / 255.0,
        .z = @intToFloat(f32, std.fmt.parseInt(u8, col[5..7], 16) catch unreachable) / 255.0,
    };
}

// https://lospec.com/palette-list/dawnbringer-16
const palette = [_]zlm.Vec3{
    parseColor("#140c1c"),
    parseColor("#442434"),
    parseColor("#30346d"),
    parseColor("#4e4a4e"),
    parseColor("#854c30"),
    parseColor("#346524"),
    parseColor("#d04648"),
    parseColor("#757161"),
    parseColor("#597dce"),
    parseColor("#d27d2c"),
    parseColor("#8595a1"),
    parseColor("#6daa2c"),
    parseColor("#d2aa99"),
    parseColor("#6dc2ca"),
    parseColor("#dad45e"),
    parseColor("#deeed6"),
};

const Vertex = extern struct {
    position: zlm.Vec3,
    color: zlm.Vec3,
};

pub fn main() anyerror!void {
    var gpa_backing = std.testing.LeakCountAllocator.init(std.heap.c_allocator);
    defer {
        gpa_backing.validate() catch |err| {};
    }
    const gpa = &gpa_backing.allocator;

    if (c.SDL_Init(c.SDL_INIT_EVERYTHING) < 0) {
        return makeSdlError();
    }
    defer _ = c.SDL_Quit();

    try sdlCheck(c.SDL_GL_SetAttribute(.SDL_GL_CONTEXT_MAJOR_VERSION, 4));
    try sdlCheck(c.SDL_GL_SetAttribute(.SDL_GL_CONTEXT_MINOR_VERSION, 5));
    try sdlCheck(c.SDL_GL_SetAttribute(.SDL_GL_CONTEXT_FLAGS, c.SDL_GL_CONTEXT_FORWARD_COMPATIBLE_FLAG | c.SDL_GL_CONTEXT_DEBUG_FLAG));

    if (cli_options.multisampling) |samples| {
        try sdlCheck(c.SDL_GL_SetAttribute(.SDL_GL_MULTISAMPLEBUFFERS, 1));
        try sdlCheck(c.SDL_GL_SetAttribute(.SDL_GL_MULTISAMPLESAMPLES, samples));
    }

    var window = c.SDL_CreateWindow(
        "HackVR Turbo",
        c.SDL_WINDOWPOS_CENTERED,
        c.SDL_WINDOWPOS_CENTERED,
        1280,
        720,
        c.SDL_WINDOW_OPENGL,
    ) orelse return makeSdlError();
    defer c.SDL_DestroyWindow(window);

    var context = c.SDL_GL_CreateContext(window) orelse return makeSdlError();
    defer _ = c.SDL_GL_DeleteContext(context);

    try sdlCheck(c.SDL_GL_MakeCurrent(window, context));

    try gl.debugMessageCallback({}, openGlDebugCallback);

    var state = hackvr.State.init(std.testing.allocator);
    defer state.deinit();

    var vao = try gl.createVertexArray();
    defer vao.delete();

    try vao.enableVertexAttribute(0);
    try vao.enableVertexAttribute(1);

    try vao.attribFormat(
        0,
        3,
        .float,
        false,
        @byteOffsetOf(Vertex, "position"),
    );
    try vao.attribFormat(
        1,
        3,
        .float,
        false,
        @byteOffsetOf(Vertex, "color"),
    );

    try vao.attribBinding(0, 0);
    try vao.attribBinding(1, 0);

    var tris_vertex_buffer = try gl.createBuffer();
    defer tris_vertex_buffer.delete();

    var lines_vertex_buffer = try gl.createBuffer();
    defer lines_vertex_buffer.delete();

    var point_vertex_buffer = try gl.createBuffer();
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

    var shader_program = try gl.createProgram();
    defer shader_program.delete();

    {
        var vertex_shader = try gl.createShader(.vertex);
        defer vertex_shader.delete();

        var fragment_shader = try gl.createShader(.fragment);
        defer fragment_shader.delete();

        try vertex_shader.source(1, &[_][]const u8{
            @embedFile("./shader/flat.vert"),
        });

        try fragment_shader.source(1, &[_][]const u8{
            @embedFile("./shader/flat.frag"),
        });

        try vertex_shader.compile();
        if ((try vertex_shader.get(.compile_status)) == 0) {
            const compile_log = try vertex_shader.getCompileLog(gpa);
            defer gpa.free(compile_log);

            std.debug.print("failed to compile vertex shader:\n{}\n", .{compile_log});
            return;
        }

        try fragment_shader.compile();
        if ((try fragment_shader.get(.compile_status)) == 0) {
            const compile_log = try fragment_shader.getCompileLog(gpa);
            defer gpa.free(compile_log);

            std.debug.print("failed to compile fragment shader:\n{}\n", .{compile_log});
            return;
        }

        try shader_program.attach(vertex_shader);
        defer shader_program.detach(vertex_shader);

        try shader_program.attach(fragment_shader);
        defer shader_program.detach(fragment_shader);

        try shader_program.link();
        if ((try shader_program.get(.link_status)) == 0) {
            const link_log = try shader_program.getCompileLog(gpa);
            defer gpa.free(link_log);

            std.debug.print("failed to compile fragment shader:\n{}\n", .{link_log});
            return;
        }
    }

    const transform_loc = (try shader_program.uniformLocation("uTransform")) orelse {
        std.log.crit(.Exe, "Failed to query uniform uTransform!\n", .{});
        return;
    };

    const highlighted_loc = (try shader_program.uniformLocation("uHighlighting")) orelse {
        std.log.crit(.Exe, "Failed to query uniform uHighlighting!\n", .{});
        return;
    };

    try gl.enable(.depth_test);
    try gl.depthFunc(.less_or_equal);
    try gl.pointSize(5.0);

    var time: f32 = 0.0;

    var hackvr_dirty = true;

    var parser = hackvr.parsing.Parser.init();

    const stdin = std.io.getStdIn().reader();
    const stderr = std.io.getStdErr().writer();
    const stdout = std.io.getStdOut().writer();

    _ = try std.os.fcntl(
        std.io.getStdIn().handle,
        std.os.F_SETFL,
        std.os.O_NONBLOCK | try std.os.fcntl(std.io.getStdIn().handle, std.os.F_GETFL, 0),
    );

    const Camera = struct {
        position: zlm.Vec3,
        pan: f32,
        tilt: f32,
    };
    var camera = Camera{
        .position = zlm.Vec3.zero,
        .pan = 0,
        .tilt = 0,
    };

    const dt = 1.0 / 60.0;

    mainLoop: while (true) : (time += dt) {
        point_list.shrink(0);

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
                            try stdout.print("# Error while parsing line: {}\n# '{}'\n", .{
                                err.error_type,
                                err.source,
                            });
                            try stderr.print("# Error while parsing line: {}\n# '{}'\n", .{
                                err.error_type,
                                err.source,
                            });
                            slice = err.rest;
                        },

                        .event => |ev| {
                            slice = ev.rest;
                            try hackvr.applyEventToState(&state, ev.event);
                            hackvr_dirty = true;
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
                            camera.pan -= @intToFloat(f32, motion.xrel) / 150.0;
                            camera.tilt -= @intToFloat(f32, motion.yrel) / 150.0;
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
                    camera.pan -= turnspeed * dt;
                }
                if (keys[c.SDL_SCANCODE_LEFT] != 0) {
                    camera.pan += turnspeed * dt;
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
                    camera.tilt += turnspeed * dt;
                }
                if (keys[c.SDL_SCANCODE_PAGEDOWN] != 0) {
                    camera.tilt -= turnspeed * dt;
                }
            }

            const pan_rot = zlm.Mat4.createAngleAxis(zlm.Vec3.unitY, camera.pan);
            const tilt_rot = zlm.Mat4.createAngleAxis(zlm.Vec3.unitX.scale(-1), camera.tilt);

            move_dir = move_dir.transformDirection(tilt_rot.mul(pan_rot));

            camera.position = camera.position.add(move_dir.scale(movespeed * dt));
        }

        // Render scene from HackVR dataset
        if (hackvr_dirty) {
            hackvr_dirty = false;

            vertex_list.shrink(0);
            poly_groups.shrink(0);

            var group_index: usize = 0;
            var groups = state.iterator();
            while (groups.next()) |group| : (group_index += 1) {
                var poly_grp = PolygonGroup{
                    .group_index = group_index,
                    .begin_tris = vertex_list.items.len,
                    .count_tris = undefined,
                    .begin_lines = outline_list.items.len,
                    .count_lines = undefined,
                    .transform = zlm.Mat4.mul(
                        zlm.Mat4.createAngleAxis(zlm.Vec3.unitY, zlm.toRadians(group.rotation.y)),
                        zlm.Mat4.createTranslation(group.translation),
                    ),
                };

                for (group.shapes.items) |shape| {
                    if (shape.points.len < 3) {
                        std.debug.print("count: {}\n", .{shape.points.len});
                    } else {
                        // Simple fan-out triangulation.
                        // Not beautiful, but very simple
                        var i: usize = 2;
                        while (i < shape.points.len) {
                            try vertex_list.append(Vertex{
                                .position = shape.points[0],
                                .color = palette[shape.attributes.color],
                            });
                            try vertex_list.append(Vertex{
                                .position = shape.points[i - 1],
                                .color = palette[shape.attributes.color],
                            });
                            try vertex_list.append(Vertex{
                                .position = shape.points[i],
                                .color = palette[shape.attributes.color],
                            });

                            i += 1;
                        }

                        i = 1;
                        while (i < shape.points.len) {
                            try outline_list.append(Vertex{
                                .position = shape.points[i - 1],
                                .color = zlm.Vec3.one,
                            });
                            try outline_list.append(Vertex{
                                .position = shape.points[i],
                                .color = zlm.Vec3.one,
                            });
                            i += 1;
                        }
                        try outline_list.append(Vertex{
                            .position = shape.points[0],
                            .color = zlm.Vec3.one,
                        });
                        try outline_list.append(Vertex{
                            .position = shape.points[shape.points.len - 1],
                            .color = zlm.Vec3.one,
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
            camera.position,
            zlm.Vec3{
                .x = std.math.sin(camera.pan) * std.math.cos(camera.tilt),
                .y = std.math.sin(camera.tilt),
                .z = -std.math.cos(camera.pan) * std.math.cos(camera.tilt),
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

            if (c.SDL_GetKeyboardState(null)[c.SDL_SCANCODE_SPACE] != 0) {
                Buffer.orig = mouse_pos_near_ws.swizzle("xyz");
                Buffer.dir = mouse_pos_far_ws.swizzle("xyz").sub(Buffer.orig).normalize();
            }
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
                const transform = zlm.Mat4.mul(
                    zlm.Mat4.createAngleAxis(zlm.Vec3.unitY, zlm.toRadians(group.rotation.y)),
                    zlm.Mat4.createTranslation(group.translation),
                );

                for (group.shapes.items) |*shape, shape_index| {
                    if (shape.points.len < 3) {
                        std.debug.print("count: {}\n", .{shape.points.len});
                    } else {
                        // Simple fan-out triangulation.
                        // Not beautiful, but very simple
                        var i: usize = 2;
                        while (i < shape.points.len) {
                            if (rayTriangleIntersect(
                                ray_origin,
                                ray_direction,
                                shape.points[0].transformPosition(transform),
                                shape.points[i - 1].transformPosition(transform),
                                shape.points[i].transformPosition(transform),
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

                            i += 1;
                        }
                        i = 0;

                        while (i < shape.points.len) {
                            try point_list.append(Vertex{
                                .position = shape.points[i].transformPosition(transform),
                                .color = parseColor("#FF0000"),
                            });
                            i += 1;
                        }
                    }
                }
            }

            {
                var step: usize = 0;
                var dist: f32 = 0.0;
                var pos = ray_origin;
                while (step < 250) : (step += 1) {
                    try point_list.append(Vertex{
                        .position = pos,
                        .color = if (dist < distance) parseColor("#FFFF00") else parseColor("#0000FF"),
                    });
                    pos = pos.add(ray_direction.scale(0.25));
                    dist += 0.25;
                }
            }

            const size = 0.1;

            if (result != null) {
                try point_list.append(Vertex{
                    .position = ray_origin.add(ray_direction.scale(distance)).sub(zlm.Vec3.unitX.scale(size)),
                    .color = parseColor("#FF00FF"),
                });
                try point_list.append(Vertex{
                    .position = ray_origin.add(ray_direction.scale(distance)).add(zlm.Vec3.unitX.scale(size)),
                    .color = parseColor("#FF00FF"),
                });
                try point_list.append(Vertex{
                    .position = ray_origin.add(ray_direction.scale(distance)).sub(zlm.Vec3.unitY.scale(size)),
                    .color = parseColor("#FF00FF"),
                });
                try point_list.append(Vertex{
                    .position = ray_origin.add(ray_direction.scale(distance)).add(zlm.Vec3.unitY.scale(size)),
                    .color = parseColor("#FF00FF"),
                });
                try point_list.append(Vertex{
                    .position = ray_origin.add(ray_direction.scale(distance)).sub(zlm.Vec3.unitZ.scale(size)),
                    .color = parseColor("#FF00FF"),
                });
                try point_list.append(Vertex{
                    .position = ray_origin.add(ray_direction.scale(distance)).add(zlm.Vec3.unitZ.scale(size)),
                    .color = parseColor("#FF00FF"),
                });
            }

            break :blk result;
        };

        if (signal_picked_shape) {
            if (picked_shape) |indices| {
                try stdout.print("{} action {}\n", .{
                    "USER",
                    indices.group.name,
                });
            }
        }

        try gl.namedBufferData(tris_vertex_buffer, Vertex, vertex_list.items, .dynamic_draw);
        try gl.namedBufferData(lines_vertex_buffer, Vertex, outline_list.items, .dynamic_draw);
        try gl.namedBufferData(point_vertex_buffer, Vertex, point_list.items, .dynamic_draw);

        // render graphics
        {
            try gl.clearColor(0.0, 0.0, 0.3, 1.0);
            try gl.clearDepth(1.0);
            try gl.clear(.{
                .color = true,
                .depth = true,
            });

            try vao.bind();
            try shader_program.use();

            try gl.programUniform1f(
                shader_program,
                highlighted_loc,
                0.0,
            );

            try vao.vertexBuffer(0, tris_vertex_buffer, 0, @sizeOf(Vertex));
            for (poly_groups.items) |poly_grp| {
                const transform = zlm.Mat4.mul(poly_grp.transform, mat_view_proj);

                try gl.programUniformMatrix4(
                    shader_program,
                    transform_loc,
                    false,
                    @ptrCast([*]const [4][4]f32, &transform.fields)[0..1],
                );

                try gl.drawArrays(.triangles, poly_grp.begin_tris, poly_grp.count_tris);
            }

            // try gl.enable(.polygon_offset_line);
            // try gl.polygonOffset(0.0, -16.0);

            try vao.vertexBuffer(0, lines_vertex_buffer, 0, @sizeOf(Vertex));
            for (poly_groups.items) |poly_grp| {
                const transform = zlm.Mat4.mul(poly_grp.transform, mat_view_proj);

                const picked = if (picked_shape) |indices|
                    indices.group_index == poly_grp.group_index
                else
                    false;

                try gl.programUniform1f(
                    shader_program,
                    highlighted_loc,
                    if (picked) @as(f32, 1.0) else @as(f32, 0.0),
                );

                try gl.programUniformMatrix4(
                    shader_program,
                    transform_loc,
                    false,
                    @ptrCast([*]const [4][4]f32, &transform.fields)[0..1],
                );
                try gl.drawArrays(.lines, poly_grp.begin_lines, poly_grp.count_lines);
            }

            try vao.vertexBuffer(0, point_vertex_buffer, 0, @sizeOf(Vertex));
            {
                var transform = mat_view_proj;
                try gl.programUniformMatrix4(
                    shader_program,
                    transform_loc,
                    false,
                    @ptrCast([*]const [4][4]f32, &transform.fields)[0..1],
                );
                try gl.drawArrays(.points, 0, point_list.items.len);
            }

            c.SDL_GL_SwapWindow(window);
            c.SDL_Delay(10);
        }
    }
}

fn openGlDebugCallback(
    source: gl.DebugSource,
    msg_type: gl.DebugMessageType,
    id: usize,
    severity: gl.DebugSeverity,
    message: []const u8,
) void {
    const msg_fmt = "[{}/{}] {}\n";
    const msg_arg = .{ @tagName(source), @tagName(msg_type), message };

    switch (severity) {
        .high => std.log.crit(.OpenGL, msg_fmt, msg_arg),
        .medium => std.log.err(.OpenGL, msg_fmt, msg_arg),
        .low => std.log.warn(.OpenGL, msg_fmt, msg_arg),
        .notification => std.log.notice(.OpenGL, msg_fmt, msg_arg),
        else => std.log.crit(.OpenGL, msg_fmt, msg_arg),
    }
}

fn isDataOnStdInAvailable() !bool {
    const stdin = std.io.getStdIn();
    if (std.builtin.os.tag == .linux) {
        var fds = [1]std.os.pollfd{
            .{
                .fd = stdin.handle,
                .events = std.os.POLLIN,
                .revents = 0,
            },
        };
        _ = try std.os.poll(&fds, 0);
        if ((fds[0].revents & std.os.POLLIN) != 0) {
            return true;
        }
    }
    if (std.builtin.os.tag == .windows) {
        std.os.windows.WaitForSingleObject(stdin.handle, 0) catch |err| switch (err) {
            error.WaitTimeOut => return false,
            else => return err,
        };
        return true;
    }
    return false;
}

fn rayTriangleIntersect(orig: zlm.Vec3, dir: zlm.Vec3, v0: zlm.Vec3, v1: zlm.Vec3, v2: zlm.Vec3) ?f32 {
    const kEpsilon = 1e-10;

    // compute plane's normal
    const v0v1 = v1.sub(v0);
    const v0v2 = v2.sub(v0);
    // no need to normalize
    const N = v0v1.cross(v0v2); // N
    const area2 = N.length();

    // Step 1: finding P

    // check if ray and plane are parallel ?
    const NdotRayDirection = N.dot(dir);
    if (std.math.absFloat(NdotRayDirection) < kEpsilon) { // almost 0
        return null; // they are parallel so they don't intersect !
    }

    // compute d parameter using equation 2
    const d = N.dot(v0);

    // compute t (equation 3)
    const t = (N.dot(orig) + d) / NdotRayDirection;
    // check if the triangle is in behind the ray
    if (t < 0) {
        return null; // the triangle is behind
    }

    // compute the intersection point using equation 1
    const P = orig.add(dir.scale(t));

    // Step 2: inside-outside test

    // edge 0
    const edge0 = v1.sub(v0);
    const vp0 = P.sub(v0);
    const C0 = edge0.cross(vp0); // vector perpendicular to triangle's plane
    const side_0 = (N.dot(C0) < 0);
    if (side_0)
        return null;

    // edge 1
    const edge1 = v2.sub(v1);
    const vp1 = P.sub(v1);
    const C1 = edge1.cross(vp1);
    const side_1 = (N.dot(C1) < 0);
    if (side_1)
        return null;

    // edge 2
    const edge2 = v0.sub(v2);
    const vp2 = P.sub(v2);
    const C2 = edge2.cross(vp2);
    const side_2 = (N.dot(C2) < 0);
    if (side_2)
        return null;

    return t; // this ray hits the triangle
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
