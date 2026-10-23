"""Observe asynchronous signal delivery without accepting surviving children."""
import time
from tools.test.supervisor import alive, identity


def assert_stopped(pid, timeout=2):
    process = identity(pid)
    if process is None:
        return
    deadline = time.monotonic() + timeout
    while alive(process) and time.monotonic() < deadline:
        time.sleep(.01)
    assert not alive(process), 'descendant survived process-group cancellation'
