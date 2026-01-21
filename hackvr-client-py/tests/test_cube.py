"""Basic tests for the client geometry."""

from hackvr_client_py.client import build_cube


def test_build_cube_vertices() -> None:
    cube = build_cube(2.0)
    assert len(cube.vertices) == 8
    assert len(cube.faces) == 6
