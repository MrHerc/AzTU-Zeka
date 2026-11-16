"""Integration-test guard: a request that makes the server log a traceback (HTTP 500) fails the test."""
import pytest


@pytest.fixture(autouse=True)
def _no_server_errors(server):
    before = len(server.errors)
    yield
    new = server.errors[before:]
    assert not new, "server logged an unexpected exception:\n" + "\n".join(new)
