
Questions needing clarification:

    If parent has scale=2 and child has pos=(1,0,0), is child's world position (2,0,0) or (1,0,0)?
    Does R_track rotate the scale axes or just the visual orientation?4. 
    
Euler Angle Singularity Handling
    Section 3.6.2 mentions gimbal lock but doesn't specify:

    What happens when interpolating through a singularity (e.g., tilt transitioning from +89° to -89°)?
    SLERP may produce unexpected visual behavior near poles
    Should transitions "go the long way" or take shortest quaternion path (which may flip unexpectedly)?

Recommendation:

    Clarify that set-object-transform $camera does NOT reset R_free
    Specify intent view-dir is the rendered camera forward (includes free-look)




Recommendation: Specify: "The new transition starts from the object's current interpolated state at command receipt time."


Missing specification:
    What's the mathematical formula for computing new local transform?
    T_world_child = T_world_old_parent * T_local_child_old
    T_world_child = T_world_new_parent * T_local_child_new
    Therefore: T_local_child_new = inverse(T_world_new_parent) * T_world_old_parent * T_local_child_old



Problem: What if text/sprite geometry has size=(0.001, 0.001) — effectively invisible?
  Still hit-testable as two triangles?
  This could create invisible click-targets (potential for abuse or confusion)

  Recommendation: Clarify whether zero-area or degenerate rectangles are hit-testable.


Recommendation: Specify: "Asset downloads may complete after object destruction; viewer may retain assets in cache. Destroying objects does not mandate canceling in-flight downloads."


But i could add that objects can't track their children in general.



25. Asset MIME Type Handling
Sections 3.5.2/3.5.3 specify URIs for fonts and images but:
Missing:

Which image formats are required? (PNG? JPEG? WebP?)
Which font formats? (TTF? WOFF2? OTF?)
What if MIME type mismatches file content?


Or document that full opacity is intentional design choice



Issue: The spec does not define behavior when reparent-object occurs during an active transition ($t > 0$).

Recommendation: Add a non-normative "Implementation Note" warning developers that they cannot split on bare LF; they must scan specifically for CR+LF.

Clarify if set-object-geometry obj null is the canonical way to hide an object without destroying it.

FAQ:
> Can a user overwrite $forward with a custom label but keep the semantic behavior?

Yes. That's mostly as viewers can bind arrow keys (or wasd, ...) to $forward and friends, but "Up" and "Forward" depend on the interpretation of the world. Thus, some worlds might need "$forward" to mean "up" (for example: climb ladder up). It could even be contextualized. Imagine a sidescrolling thing where you walk to a lever, and "$forward" (Up key) changes to "Use lever", you walk right to a ladder and it changes to "Climb stairs". You walk further, and it gets disabled as there's no interaction.

FAQ:
  This is due to free-look interaction with $forward: Imagine a game like "Eye of the Beholder" or "Legend of Grimrock" where the player can look around, and then move forward/backward and use verbs like attack and such. This works also well with the $foward + view-dir option.

FAQ:
  You can also just use tagging or smart object naming with globbing:

  variant 1:
  ```
  remove-triangles  <hot reload geom> grp-1-*
  add-triangle <hot reload geom> grp-1-5 …
  ```

  variant 2:
  ```
  create-geometry reload-type_a-gen-2 …
  set-object-geometry *-type_a-* reload-type_a-gen-2
  destroy-geometry reload-type_a-gen-1
  ```

Recommendation: The spec must define a fallback behavior or a secondary up-hint (e.g., "Use Local Up, unless target is within 1 degree of Local Up, then use Local Z/Forward"). Alternatively, accept the gimbal lock as a known limitation.


Coordinate System: Rewrite Section 1.2. Define the new basis ($+Z$ Up). Explicitly define rotation sign direction (Clockwise vs. Counter-Clockwise) to resolve the "Intuition" requirement.

### Protocol Adjustment: Coordinate System

Since you are leaning towards the intuitive ** Up** system, here is the clean definition for the spec update:

**1.2 Coordinate System (Draft Proposal)**

* **Basis:** Right-Handed Z-Up.
  * +X: Right
  * +Y: Forward (into the screen/world)
  * +Z: Up
* **Rotation (The "Intuitive" Convention):**
  * All rotations are defined in **degrees**.
  * **Pan:** Rotation around Global Z (). **Positive = Clockwise** (turning Right).
    * *Note: This effectively inverts the standard mathematical Right-Hand Rule for this axis.*
  * **Tilt:** Rotation around Local X (). **Positive = Look Up**.
  * **Roll:** Rotation around Local Y (). **Positive = Tilt Head Right**.



You define compositions like T_world(obj) = parent ∘ pos ∘ R_track ∘ R_local ∘ scale and R_render = R_track($camera) ∘ R_local($camera) ∘ R_free, but you never define whether A ∘ B means “apply A then B” or the reverse. This is not a style issue—different implementations will produce different results. It’s especially critical for the camera: your text says free-look is an “additive local offset”, which usually implies it is applied last in the chain, but the written composition could be read either way. Add an explicit, normative definition with at least 2–3 numeric test vectors. 


if expansion exceeds local limits, the receiver MUST ignore the entire command (no partial application). 


Resynchronization after framing violations: You say “stray CR” / invalid UTF-8 / etc. are “command errors” and ignored after establishment, but you don’t define how a receiver finds the next command boundary in the presence of malformed bytes or overlong lines. In practice, you want a normative rule like:

Empty command name: The EBNF allows empty name; later you only say it “should be non-empty”. Make it MUST be non-empty if you want interoperable parsing.

Raw connections have a strict hackvr-hello exchange and version negotiation. HTTP Upgrade uses a header HackVr-Version: v1 and says HTTP “pins to v1”, and then the command stream begins immediately after headers. That’s workable, but you should explicitly state that hackvr-hello MUST NOT appear on the HTTP-upgraded stream (or MUST appear). Right now it’s implied but not pinned down, and implementers may try to unify both paths. 


Even a minimal rule (“viewers MAY follow redirects; if they do, origin binding uses the final upgraded request”) would remove ambiguity. 



Origin binding definition needs normalization rules: you bind session tokens to (domain, port, path, query) or Host + request-target, but don’t define canonicalization (case-folding host, default ports, percent-encoding normalization, punycode, etc.). Without this, two viewers can disagree whether a token is “same-origin bound”.



You specify “front-to-back by depth” and that tagged triangles behind untagged opaque geometry aren’t clickable. That implies the viewer uses the actual depth-tested rendered surface for hit-testing. Make that explicit


Text layout is underspecified: “contain” fit inside rectangle is a start, but you should define minimum expectations: wrapping vs no wrapping, alignment defaults, and what happens on overflow (scale down? clip? ellipsis?). If you want maximal freedom, say so explicitly to prevent servers relying on a specific layout. 


Sprites and alpha: You say sprites “depth-test like opaque geometry”, but images often contain transparency. Define whether alpha affects:
- picking: no
- depth writes: yes (may be rendered depth-tested)



But $camera reparenting is not explicitly allowed or forbidden; some implementations will allow it and others won’t. Decide and specify (both choices are defensible). 
$camera is just an object like any other. 