For every change in this repository, the following must pass via the justfile:
- just test
- just lint
- just package

If `just` is not installed, read the justfile to determine the equivalent commands
and run those commands manually.

Install the requirements from requirements.txt before running the commands.

Use a virtual environment when possible.

After changing code, always report the total code coverage (excluding tests/) in your final response.
Code under hackvr-py/src must always have 100% test coverage.

## Lessons learned
- Prefer exercising behavior through public APIs; avoid importing or testing private helpers just to gain coverage.
- When a branch is unreachable through the public interface, replace it with an assertion that documents the invariant instead of writing tests for private functions.
- After changing code, always re-read the surrounding logic to see if the changes enable optimizations or simplifications; for example, calling `_optional_empty(allow_empty=True)` is a no-op because the caller already permits empty values, so it should be avoided.
