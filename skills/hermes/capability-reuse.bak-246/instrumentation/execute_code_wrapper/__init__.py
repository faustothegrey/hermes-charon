"""Thin passive wrapper for execute_code-like callables. Does not change behavior."""
import time
from instrumentation import observer

def wrap_execute_code(callable_):
    def wrapped(code, *args, session_id="", task_id="", **kwargs):
        observer.observe_execute_code_start(code, session_id=session_id, task_id=task_id)
        start = time.monotonic()
        try:
            result = callable_(code, *args, **kwargs)
            return result
        finally:
            observer.observe_execute_code_complete(code, locals().get("result"), (time.monotonic() - start) * 1000)
    return wrapped
