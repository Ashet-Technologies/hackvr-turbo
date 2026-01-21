"""Raylib-based HackVR client skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, sin
from pathlib import Path

import pyray as rl


@dataclass
class CameraState:
    """Track camera orbit state."""

    yaw: float = 0.0
    pitch: float = 0.0
    radius: float = 6.0


@dataclass
class CubeGeometry:
    """Cube vertex and triangle data."""

    vertices: list[tuple[float, float, float]]
    faces: list[tuple[int, int, int, int]]


def build_cube(size: float) -> CubeGeometry:
    """Create cube vertices and faces."""
    half = size / 2.0
    vertices = [
        (-half, -half, -half),
        (half, -half, -half),
        (half, half, -half),
        (-half, half, -half),
        (-half, -half, half),
        (half, -half, half),
        (half, half, half),
        (-half, half, half),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 5, 6, 7),
        (0, 4, 7, 3),
        (1, 5, 6, 2),
        (3, 2, 6, 7),
        (0, 1, 5, 4),
    ]
    return CubeGeometry(vertices=vertices, faces=faces)


def rotate_point(point: tuple[float, float, float], pitch: float, yaw: float) -> tuple[float, float, float]:
    """Rotate a point around the X and Y axes."""
    x, y, z = point
    cos_yaw = cos(yaw)
    sin_yaw = sin(yaw)
    xz = x * cos_yaw - z * sin_yaw
    zz = x * sin_yaw + z * cos_yaw

    cos_pitch = cos(pitch)
    sin_pitch = sin(pitch)
    yz = y * cos_pitch - zz * sin_pitch
    zz = y * sin_pitch + zz * cos_pitch

    return xz, yz, zz


def draw_manual_cube(center: rl.Vector3, cube: CubeGeometry, pitch: float, yaw: float) -> None:
    """Draw a cube using explicit triangles."""
    colors = [
        rl.RED,
        rl.BLUE,
        rl.GREEN,
        rl.ORANGE,
        rl.PURPLE,
        rl.YELLOW,
    ]
    rotated_vertices = []
    for vertex in cube.vertices:
        rx, ry, rz = rotate_point(vertex, pitch, yaw)
        rotated_vertices.append(rl.Vector3(center.x + rx, center.y + ry, center.z + rz))

    for color, face in zip(colors, cube.faces, strict=False):
        a, b, c, d = face
        rl.draw_triangle_3d(rotated_vertices[a], rotated_vertices[b], rotated_vertices[c], color)
        rl.draw_triangle_3d(rotated_vertices[a], rotated_vertices[c], rotated_vertices[d], color)


def update_camera(camera: rl.Camera3D, state: CameraState) -> None:
    """Update camera position from mouse input."""
    if rl.is_mouse_button_down(rl.MOUSE_BUTTON_RIGHT):
        delta = rl.get_mouse_delta()
        state.yaw -= delta.x * 0.01
        state.pitch -= delta.y * 0.01
        state.pitch = max(-1.2, min(1.2, state.pitch))

    x = state.radius * cos(state.pitch) * sin(state.yaw)
    y = state.radius * sin(state.pitch)
    z = state.radius * cos(state.pitch) * cos(state.yaw)
    camera.position = rl.Vector3(x, y, z)


def run_client(address: str) -> None:
    """Run the main client loop."""
    window_width = 1024
    window_height = 768
    rl.init_window(window_width, window_height, f"HackVR Client - {address}")
    rl.set_target_fps(60)

    camera = rl.Camera3D(
        rl.Vector3(5.0, 4.0, 5.0),  # position
        rl.Vector3(0.0, 0.0, 0.0),  # target
        rl.Vector3(0.0, 1.0, 0.0),  # up
        45.0,  # fovy
        rl.CAMERA_PERSPECTIVE,  # projection
    )
    camera_state = CameraState(yaw=0.7, pitch=0.3)

    cube = build_cube(1.5)
    cube_spin = 0.0

    asset_path = Path(__file__).resolve().parents[2] / "assets" / "picsum_26_300x200.jpg"
    if not asset_path.exists():
        message = f"Missing texture at {asset_path}. Download https://picsum.photos/id/26/300/200 to that path."
        raise FileNotFoundError(message)
    image_texture = rl.load_texture(str(asset_path))

    text_texture = rl.load_render_texture(256, 128)

    while not rl.window_should_close():
        cube_spin += 0.02
        update_camera(camera, camera_state)

        rl.begin_texture_mode(text_texture)
        rl.clear_background(rl.BLANK)
        rl.draw_text("HackVR", 40, 40, 32, rl.WHITE)
        rl.draw_text("client", 40, 80, 24, rl.SKYBLUE)
        rl.end_texture_mode()

        rl.begin_drawing()
        rl.clear_background(rl.RAYWHITE)
        rl.begin_mode_3d(camera)

        draw_manual_cube(rl.Vector3(0.0, 0.0, 0.0), cube, cube_spin, cube_spin * 0.7)

        rl.draw_grid(10, 1.0)
        rl.draw_billboard(camera, image_texture, rl.Vector3(-2.5, 1.0, 0.0), 2.0, rl.WHITE)
        rl.draw_billboard(camera, text_texture.texture, rl.Vector3(2.5, 1.0, 0.0), 2.0, rl.WHITE)

        rl.end_mode_3d()
        rl.draw_text("Right mouse to orbit", 10, 10, 18, rl.DARKGRAY)
        rl.end_drawing()

    rl.unload_texture(image_texture)
    rl.unload_render_texture(text_texture)
    rl.close_window()
