# HackVR Spec TODO (curated)

## Transform math & scene graph

T01. Define the meaning of the composition operator (∘) used in transform chains (apply order + matrix/vector convention) and provide 2–3 numeric test vectors (including parent scaling affecting child position and whether scaling axes are rotated by R_track/R_local).
T02. Specify the exact math for `reparent-object ... world` (how to recompute a child’s local transform from old/new parents), including how scale is handled.
T03. Define semantics when `reparent-object` is issued while the child is mid-transition (`set-object-transform ... t>0`): whether transitions (per channel) continue in world-space, are converted to new local space, or are canceled/restarted.

## Transitions & rotation edge cases

T04. Document Euler singularity behavior for transitions (tilt ≈ ±90°): confirm shortest-path quaternion interpolation, define tie-breaks (q vs -q), and warn that Euler-authoring intuition may not hold near poles.
T05. For `track-object ... focus`, define behavior when the target direction is near the up vector (up-hint degeneracy): specify a fallback up-hint strategy or explicitly declare the limitation.

## Interaction, picking & UI geometry

T06. Specify minimum expectations (or explicitly “viewer-defined”) for text layout: wrapping, alignment defaults, and overflow behavior (clip/scale/ellipsis).

## Limits & robustness

T07. Specify behavior when selector expansion would exceed viewer limits: ignore whole command vs partial application vs truncation; align with the “no partial state changes on command error” rule.
