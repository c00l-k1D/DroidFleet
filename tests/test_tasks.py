from app.tasks.repository import TaskRepository


def test_tasks_are_persisted(tmp_path):
    repository = TaskRepository(tmp_path / "tasks.json")
    tasks = [{"name": "Nightly", "target": "Без группы", "action": "Screenshot", "status": "SCHEDULED"}]
    repository.save(tasks)
    assert repository.load() == tasks
