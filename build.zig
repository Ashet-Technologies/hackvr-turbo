const std = @import("std");

const hackvr = std.build.Pkg{
    .name = "hackvr",
    .path = "lib/hackvr/lib.zig",
};

pub fn build(b: *std.build.Builder) void {
    // Standard target options allows the person running `zig build` to choose
    // what target to build for. Here we do not override the defaults, which
    // means any target is allowed, and the default is native. Other options
    // for restricting supported target set are available.
    const target = b.standardTargetOptions(.{});

    // Standard release options allow the person running `zig build` to select
    // between Debug, ReleaseSafe, ReleaseFast, and ReleaseSmall.
    const mode = b.standardReleaseOptions();

    const exe = b.addExecutable("hackvr-zig", "src/main.zig");
    exe.setTarget(target);
    exe.setBuildMode(mode);

    exe.linkSystemLibrary("SDL2");
    exe.linkSystemLibrary("epoxy");

    exe.addPackage(hackvr);

    exe.install();

    const test_step = b.step("test", "Runs all tests");
    test_step.dependOn(&b.addTest("lib/hackvr/lib.zig").step);

    const run_cmd = exe.run();
    run_cmd.step.dependOn(b.getInstallStep());

    const run_step = b.step("run", "Run the app");
    run_step.dependOn(&run_cmd.step);
}
