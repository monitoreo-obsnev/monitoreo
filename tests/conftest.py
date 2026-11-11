"""Fixtures of every test: no test reads the study areas that the developer added to their own assistant
(~/MonitorEO/capas), which would change the instructions of the model and break the tests that compare them; and no
test reads the STAC records of the Earth Engine data catalog on the internet (monitoreo.assets): those a test needs,
it gives them."""

import pytest


@pytest.fixture(autouse=True)
def empty_layers(tmp_path, monkeypatch):
	"""The study areas of the assistant in an empty folder of the test, not in ~/MonitorEO/capas."""
	from monitoreo import assistant
	monkeypatch.setattr(assistant, 'LAYERS', str(tmp_path / 'capas'))


@pytest.fixture(autouse=True)
def no_stac(request, monkeypatch):
	"""No STAC record from the internet, and none remembered from another test (except in the tests marked ee)."""
	from monitoreo import assets, references
	if 'ee' not in request.keywords:
		monkeypatch.setattr(assets, '_fetch_json', lambda url, timeout=10: None)
	monkeypatch.setattr(assets, '_stac', {})
	monkeypatch.setattr(assets, '_info', {})
	monkeypatch.setattr(references, 'DATA', {})
