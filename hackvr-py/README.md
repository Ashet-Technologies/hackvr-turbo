# hackvr-py

Python helpers for the HackVR protocol.

## Usage

If you're working on the package without installing it into a venv, you can use `PYTHONPATH=src` to allow
loading the package data:

```sh-session
[user@work hackvr-py]$ export "PYTHONPATH=$(pwd)/src"
[user@work hackvr-py]$ python src/hackvr/tools/playback_server.py --help
```
