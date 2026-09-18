import os

DEFAULT_GRPC_PORT = 50051


def grpc_port() -> int:
    return int(os.getenv("GRPC_PORT", str(DEFAULT_GRPC_PORT)))
