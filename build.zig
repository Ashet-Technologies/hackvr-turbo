const std = @import("std");

const hackvr = std.build.Pkg{
    .name = "hackvr",
    .path = .{ .path = "lib/hackvr/lib.zig" },
    .dependencies = &[_]std.build.Pkg{zlm},
};

const zlm = std.build.Pkg{
    .name = "zlm",
    .path = .{ .path = "lib/zlm/zlm.zig" },
};

const zgl = std.build.Pkg{
    .name = "zgl",
    .path = .{ .path = "lib/zgl/zgl.zig" },
};

const args = std.build.Pkg{
    .name = "zig-args",
    .path = .{ .path = "lib/zig-args/args.zig" },
};

pub fn build(b: *std.build.Builder) void {
    const target = b.standardTargetOptions(.{});
    const mode = b.standardReleaseOptions();

    const exe = b.addExecutable("hackvr", "src/main.zig");
    exe.setTarget(target);
    exe.setBuildMode(mode);

    exe.linkLibC();
    exe.linkSystemLibrary("SDL2");
    exe.linkSystemLibrary("epoxy");

    exe.addPackage(hackvr);
    exe.addPackage(zlm);
    exe.addPackage(zgl);
    exe.addPackage(args);

    exe.install();

    const hackvr_tests = b.addTest("lib/hackvr/lib.zig");
    hackvr_tests.addPackage(zlm);

    const test_step = b.step("test", "Runs all tests");
    test_step.dependOn(&hackvr_tests.step);

    const run_cmd = exe.run();
    run_cmd.step.dependOn(b.getInstallStep());

    const run_step = b.step("run", "Run the app");
    run_step.dependOn(&run_cmd.step);
}
