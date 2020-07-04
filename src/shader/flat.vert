#version 330

layout(location = 0) in vec3 vPosition;
layout(location = 1) in vec3 vColor;

out vec3 color;

uniform mat4 uTransform;

void main() {
  gl_Position = uTransform * vec4(vPosition, 1);
  color = vColor;
}