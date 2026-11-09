"""Fixtures of every test: no test reads the study areas that the developer added to their own assistant
(~/MonitorEO/capas), which would change the instructions of the model and break the tests that compare them."""

import pytest


@pytest.fixture(autouse=True)
def empty_layers(tmp_path, monkeypatch):
	"""The study areas of the assistant in an empty folder of the test, not in ~/MonitorEO/capas."""
	from monitoreo import assistant
	monkeypatch.setattr(assistant, 'LAYERS', str(tmp_path / 'capas'))
