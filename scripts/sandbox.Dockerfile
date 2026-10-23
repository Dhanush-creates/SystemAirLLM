# Sandbox image for agent-written code: Python with the common engineering libraries.
# Built once by setup (needs internet) or loaded from offline\sandbox-image.tar.
# Containers from it are always started with --network none.
FROM python:3.12-slim
RUN pip install --no-cache-dir numpy pandas sympy openpyxl
WORKDIR /work
