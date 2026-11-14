"""The PNG previews of the maps, without Earth Engine: computed on the pixels of the data when they are coarser than
those of the preview, the message of Earth Engine when it cannot make one, and the map without its preview then
(the assistant showed «HTTPError: HTTP Error 400: Bad Request» for the map of the cloud frequency of MODIS of
2001-2025 over La Palma, and the map was lost)."""

import io
import json
import urllib.error

import ee
import pytest

from monitoreo import maps, services

LA_PALMA = [-18.01, 28.45, -17.72, 28.86]  # [w, s, e, n]: about 45 km from north to south


class Img:
	"""An image of Earth Engine that records what is done with it."""

	def __init__(self, url='https://earthengine.googleapis.com/v1/thumbnails/x:getPixels'):
		self.url, self.done = url, []

	def reproject(self, projection):
		self.done.append(('reproject', projection))
		return self

	def visualize(self, **vis):
		self.done.append(('visualize', vis))
		return self

	def getThumbURL(self, params):
		self.done.append(('thumb', params))
		return self.url


class FakeEE:
	"""ee, for maps.coarse and maps.thumbnail."""
	EEException = ee.EEException

	@staticmethod
	def Image(image):
		return image

	class Projection:
		def __init__(self, crs):
			self.crs = crs

		def atScale(self, scale):
			return (self.crs, scale)


@pytest.fixture
def fake_ee(monkeypatch):
	monkeypatch.setattr(maps, 'ee', FakeEE)


def test_coarse_data_on_their_own_pixels(fake_ee):
	img = Img()
	# MODIS (1 km) over La Palma: 45 pixels of the data instead of 768 of the preview, hundreds of times fewer
	assert maps.coarse(img, 1000, LA_PALMA) is img and img.done == [('reproject', ('EPSG:4326', 1000.0))]
	for scale in (10, 30):  # Sentinel-2 and Landsat: the pixels of the preview (about 60 m) are coarser already
		img = Img()
		assert maps.coarse(img, scale, LA_PALMA) is img and img.done == []
	img = Img()
	assert maps.coarse(img, None, LA_PALMA) is img and maps.coarse(img, 1000, None) is img and img.done == []
	assert maps.coarse(img, 1000, [-10, 35, 4, 44]) is img and img.done == []  # Spain: 1.5 km pixels in the preview


def _http_error(body):
	return urllib.error.HTTPError('https://earthengine.googleapis.com', 400, 'Bad Request', {}, io.BytesIO(body))


def test_the_message_of_earth_engine(fake_ee, monkeypatch):
	body = json.dumps({'error': {'code': 400, 'message': 'Computation timed out.', 'status': 'INVALID_ARGUMENT'}})

	def refused(url, timeout):
		raise _http_error(body.encode())

	monkeypatch.setattr(maps.urllib.request, 'urlopen', refused)
	with pytest.raises(ee.EEException, match='could not make the PNG preview: Computation timed out.$'):
		maps.thumbnail(Img(), 'region', {'min': 0, 'max': 1})
	assert maps.earth_engine_error(_http_error(b'Not JSON')) == 'Not JSON'
	assert 'HTTP Error 400' in maps.earth_engine_error(_http_error(b''))

	def slow(url, timeout):
		assert timeout == maps.PREVIEW_TIMEOUT
		raise TimeoutError('The read operation timed out')

	monkeypatch.setattr(maps.urllib.request, 'urlopen', slow)
	with pytest.raises(ee.EEException, match='did not make the PNG preview in 5 minutes'):
		maps.thumbnail(Img(), 'region')

	def not_connected(url, timeout):
		raise urllib.error.URLError(TimeoutError('timed out'))

	monkeypatch.setattr(maps.urllib.request, 'urlopen', not_connected)
	with pytest.raises(ee.EEException, match='in 5 minutes'):
		maps.thumbnail(Img(), 'region')


class Regions:
	def geometry(self):
		return self

	def bounds(self):
		return 'bounds'


def test_the_map_without_its_preview(monkeypatch, tmp_path):
	seen = []
	monkeypatch.setattr(maps, 'coarse', lambda img, res, bounds: seen.append((res, bounds)) or img)
	monkeypatch.setattr(maps, 'with_outline', lambda img, vis, regions: img)

	def refused(img, region, vis=None, dimensions=768, path=None):
		raise ee.EEException('Earth Engine could not make the PNG preview: Computation timed out.')

	monkeypatch.setattr(maps, 'thumbnail', refused)
	out = {'url': 'https://ee/{z}/{x}/{y}', 'bounds': LA_PALMA, 'thumbnail': None}
	png = str(tmp_path / 'map.png')
	res = services._preview(dict(out), Img(), {}, Regions(), 1000, png)
	assert res['url'] == out['url'] and res['thumbnail'] is None  # the map, by its tiles
	assert res['thumbnail_error'] == 'Earth Engine could not make the PNG preview: Computation timed out.'
	assert seen == [(1000, LA_PALMA)]  # on the pixels of the data, if they are the coarser

	monkeypatch.setattr(maps, 'thumbnail', lambda img, region, vis=None, dimensions=768, path=None: b'png')
	res = services._preview(dict(out), Img(), {}, Regions(), 1000, png)
	assert res['thumbnail'] == png and 'thumbnail_error' not in res
	assert services._preview(dict(out), Img(), {}, Regions(), 1000, None) == out  # quick: no preview asked for


def test_the_mcp_server_without_the_preview(tmp_path):
	from monitoreo import mcp_server
	assert mcp_server._preview({'url': 'u', 'thumbnail': None, 'thumbnail_error': 'timed out'}) == []
	png = tmp_path / 'map.png'
	png.write_bytes(b'\x89PNG')
	images = mcp_server._preview({'url': 'u', 'thumbnail': str(png)})
	assert len(images) == 1
	assert 'do not ask for it again' in ' '.join(mcp_server.INSTRUCTIONS.split())
