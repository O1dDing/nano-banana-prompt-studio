import threading
import time
from unittest.mock import patch

from nano_banana.web.image_tasks import ImageTaskManager


def wait_for(manager, task_id, terminal=("completed", "failed", "cancelled")):
    for _ in range(500):
        task = manager.get(task_id)
        if task and task["status"] in terminal:
            return task
        time.sleep(0.005)
    raise AssertionError(f"task {task_id} did not finish")


def test_two_tasks_have_independent_ids_and_results():
    with patch.dict(
        "os.environ",
        {"IMAGE_TASK_WORKERS": "2", "IMAGE_TASK_MAX_PENDING": "8"},
    ):
        manager = ImageTaskManager()
    first = manager.submit(lambda: "image-a", provider="a", model="m1")
    second = manager.submit(lambda: "image-b", provider="b", model="m2")

    first_done = wait_for(manager, first["task_id"])
    second_done = wait_for(manager, second["task_id"])
    assert first["task_id"] != second["task_id"]
    assert first_done["image"] == "image-a"
    assert second_done["image"] == "image-b"


def test_queued_task_can_be_cancelled_without_running():
    blocker_started = threading.Event()
    release_blocker = threading.Event()
    second_ran = threading.Event()

    with patch.dict(
        "os.environ",
        {"IMAGE_TASK_WORKERS": "1", "IMAGE_TASK_MAX_PENDING": "8"},
    ):
        manager = ImageTaskManager()

    def blocker():
        blocker_started.set()
        release_blocker.wait(timeout=3)
        return "first"

    def second_runner():
        second_ran.set()
        return "second"

    first = manager.submit(blocker, provider="a", model="m1")
    assert blocker_started.wait(timeout=1)
    second = manager.submit(second_runner, provider="b", model="m2")
    cancelled = manager.cancel(second["task_id"])
    assert cancelled["status"] == "cancelled"

    release_blocker.set()
    assert wait_for(manager, first["task_id"])["status"] == "completed"
    assert wait_for(manager, second["task_id"])["status"] == "cancelled"
    assert not second_ran.is_set()
