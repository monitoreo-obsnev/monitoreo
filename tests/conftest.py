"""Fixtures of every test: no test reads the study areas nor the documents that the developer added to their own
assistant (~/MonitorEO/capas, ~/MonitorEO/documentos), which would change the instructions or the conversation of the
model and break the tests that compare them."""

import pytest


@pytest.fixture(autouse=True)
def empty_layers(tmp_path, monkeypatch):
	"""The study areas and the documents of the assistant in empty folders of the test, not in ~/MonitorEO."""
	from monitoreo import assistant
	monkeypatch.setattr(assistant, 'LAYERS', str(tmp_path / 'capas'))
	monkeypatch.setattr(assistant, 'DOCUMENTS', str(tmp_path / 'documentos'))
