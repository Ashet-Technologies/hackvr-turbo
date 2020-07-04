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

    const PolygonGroup = struct {
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

    try gl.enable(.depth_test);
    try gl.depthFunc(.less_or_equal);
    try gl.enable(.polygon_offset_line);
    try gl.polygonOffset(0.0, -16.0);

    var time: f32 = 0.0;

    var hackvr_dirty = true;

    var parser = hackvr.parsing.Parser.init();

    const stdin = std.io.getStdIn().reader();
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
                            try stdout.print("# Error while parsing line: {}\n", .{
                                err.error_type,
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

        // process SDL events
        {
            var event: c.SDL_Event = undefined;
            while (c.SDL_PollEvent(&event) != 0) {
                switch (event.type) {
                    c.SDL_QUIT => break :mainLoop,
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

            var groups = state.iterator();
            while (groups.next()) |group| {
                var poly_grp = PolygonGroup{
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

            try gl.namedBufferData(tris_vertex_buffer, Vertex, vertex_list.items, .dynamic_draw);
            try gl.namedBufferData(lines_vertex_buffer, Vertex, outline_list.items, .dynamic_draw);
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

            try vao.vertexBuffer(0, lines_vertex_buffer, 0, @sizeOf(Vertex));
            for (poly_groups.items) |poly_grp| {
                const transform = zlm.Mat4.mul(poly_grp.transform, mat_view_proj);

                try gl.programUniformMatrix4(
                    shader_program,
                    transform_loc,
                    false,
                    @ptrCast([*]const [4][4]f32, &transform.fields)[0..1],
                );
                try gl.drawArrays(.lines, poly_grp.begin_lines, poly_grp.count_lines);
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
