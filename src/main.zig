const std = @import("std");

const hackvr = @import("hackvr");

const c = @cImport({
    @cInclude("epoxy/gl.h");
    @cInclude("SDL.h");
    // @cInclude("SDL_opengl.h");
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
    .multisampling = null,
};

pub fn main() anyerror!void {
    if (c.SDL_Init(c.SDL_INIT_EVERYTHING) < 0) {
        return makeSdlError();
    }
    defer _ = c.SDL_Quit();

    try sdlCheck(c.SDL_GL_SetAttribute(.SDL_GL_CONTEXT_MAJOR_VERSION, 4));
    try sdlCheck(c.SDL_GL_SetAttribute(.SDL_GL_CONTEXT_MINOR_VERSION, 5));
    try sdlCheck(c.SDL_GL_SetAttribute(.SDL_GL_CONTEXT_FLAGS, c.SDL_GL_CONTEXT_FORWARD_COMPATIBLE_FLAG | c.SDL_GL_CONTEXT_DEBUG_FLAG));

    if (cli_options.multisampling) |samples| {
        try sdlCheck(c.SDL_GL_SetAttribute(c.SDL_GL_MULTISAMPLEBUFFERS, 1));
        try sdlCheck(c.SDL_GL_SetAttribute(c.SDL_GL_MULTISAMPLESAMPLES, samples));
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

    c.glDebugMessageCallback(openGlDebugCallback, null);

    mainLoop: while (true) {
        // process events
        {
            var event: c.SDL_Event = undefined;
            while (c.SDL_PollEvent(&event) != 0) {
                switch (event.type) {
                    c.SDL_QUIT => break :mainLoop,
                    else => std.log.notice(.HackVR, "Unhandled event: {}\n", .{event.type}),
                }
            }
        }

        {
            // render
            c.glClearColor(1.0, 0.0, 0.0, 1.0);
            c.glClear(c.GL_COLOR_BUFFER_BIT);

            c.SDL_GL_SwapWindow(window);
            c.SDL_Delay(10);
        }
    }
}

fn openGlDebugCallback(
    source: c.GLenum,
    msg_type: c.GLenum,
    id: c.GLuint,
    severity: c.GLenum,
    length: c.GLsizei,
    message: [*c]const c.GLchar,
    userParam: ?*const c_void,
) callconv(.C) void {
    const msg_fmt = "{}\n";
    const msg_arg = .{
        message.?[0..@intCast(usize, length)],
    };

    switch (severity) {
        c.GL_DEBUG_SEVERITY_HIGH => std.log.err(.OpenGL, msg_fmt, msg_arg),
        c.GL_DEBUG_SEVERITY_MEDIUM => std.log.warn(.OpenGL, msg_fmt, msg_arg),
        c.GL_DEBUG_SEVERITY_LOW => std.log.notice(.OpenGL, msg_fmt, msg_arg),
        c.GL_DEBUG_SEVERITY_NOTIFICATION => std.log.notice(.OpenGL, msg_fmt, msg_arg),
        else => std.log.crit(.OpenGL, msg_fmt, msg_arg),
    }
}
