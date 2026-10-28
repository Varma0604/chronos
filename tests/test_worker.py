from app.worker import execute


def test_builtin_task_handlers():
    assert execute("echo", {"value": "hi"}) == "hi"
    assert execute("sum", {"values": [2, 3, 4]}) == 9
