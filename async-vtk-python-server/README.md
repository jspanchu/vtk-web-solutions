# Async VTK Python Server

This is a demo of an asynchronous VTK Python server using the `vtk-web-solutions` library. It allows you to load VTK files asynchronously and interact with them in a web interface.

See the [Engine](core/Engine.cxx) class for integration with Python `asyncio` module.

## Build

First, create a Python virtual environment and activate it:

```bash
uv venv -p 3.13 .venv
source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
```

Then, run this command that builds the C++ engine and installs it in the venv.

```bash
uv pip install . --extra-index-url  https://vtk.org/files/wheel-sdks
```

## Run
To run the server, execute the following command:

```bash
python server.py
```
