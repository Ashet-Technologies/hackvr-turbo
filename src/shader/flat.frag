#version 330

layout(location = 0) out vec4 fColor;

in vec3 color;

uniform float uHighlighting;

void main() {
  // comment
  fColor = mix(vec4(color, 1.0), vec4(1, 0, 0, 1), uHighlighting);
}