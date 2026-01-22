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
