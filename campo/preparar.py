"""Copia a app/src/main/assets/www/lib lo que la app usa sin modificar:

  catalog.js y core.js   de gee/ de monitoreo (el mismo cálculo que la app de Earth Engine y el paquete de Python)
  ee_api_js.js           cliente JS de Earth Engine (@google/earthengine, la versión de gee/package.json)
  leaflet                mapa
  chart.umd.js           gráficos

    python preparar.py              solo catalog.js y core.js (tras actualizar el repositorio monitoreo)
    python preparar.py --check      solo comprueba que lib/ tiene el núcleo de monitoreo (sale con error si no)
    python preparar.py --npm DIR    también las librerías; DIR: carpeta con los paquetes de npm extraídos (npm pack + tar)

gee/ se busca, por orden, en la variable de entorno MONITOREO (la carpeta del repositorio monitoreo), en ../gee (la app
dentro de monitoreo, en campo/) y en ../monitoreo/gee (la app en su propio repositorio, junto a monitoreo).
La compilación de Android (app/build.gradle) hace la misma copia antes de compilar.
"""

import argparse
import filecmp
import glob
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, 'app', 'src', 'main', 'assets', 'www', 'lib')
CORE = ('catalog.js', 'core.js')


def gee_dir():
	"""La carpeta gee/ de monitoreo de la que la app toma su núcleo."""
	options = []
	if os.environ.get('MONITOREO'):
		options.append(os.path.join(os.environ['MONITOREO'], 'gee'))
	options += [os.path.join(HERE, '..', 'gee'), os.path.join(HERE, '..', 'monitoreo', 'gee')]
	for d in options:
		if all(os.path.isfile(os.path.join(d, n)) for n in CORE):
			return os.path.normpath(d)
	raise SystemExit('no encuentro gee/ de monitoreo en: ' + ', '.join(os.path.normpath(d) for d in options))


def one(pattern):
	found = sorted(glob.glob(pattern))
	if not found:
		raise SystemExit('no encuentro ' + pattern)
	return found[-1]


def main():
	p = argparse.ArgumentParser()
	p.add_argument('--npm')
	p.add_argument('--check', action='store_true')
	a = p.parse_args()
	gee = gee_dir()
	if a.check:
		old = [n for n in CORE if not filecmp.cmp(os.path.join(gee, n), os.path.join(LIB, n), shallow=False)]
		if old:
			raise SystemExit('lib/ no tiene el núcleo de ' + gee + ': ' + ', '.join(old) + '; ejecuta python preparar.py')
		print('lib/ tiene el núcleo de', gee)
		return
	os.makedirs(LIB, exist_ok=True)
	for name in CORE:
		shutil.copy(os.path.join(gee, name), LIB)
	if not a.npm:
		print('catalog.js y core.js copiados de', gee)
		return
	shutil.copy(one(os.path.join(a.npm, 'google-earthengine-*', 'package', 'build', 'ee_api_js.js')), LIB)
	shutil.copy(one(os.path.join(a.npm, 'chart.js-*', 'package', 'dist', 'chart.umd.js')), LIB)
	leaflet = one(os.path.join(a.npm, 'leaflet-*', 'package', 'dist'))
	dest = os.path.join(LIB, 'leaflet')
	shutil.rmtree(dest, ignore_errors=True)
	os.makedirs(dest)
	for name in ('leaflet.js', 'leaflet.css'):
		shutil.copy(os.path.join(leaflet, name), dest)
	shutil.copytree(os.path.join(leaflet, 'images'), os.path.join(dest, 'images'))
	for f in sorted(os.listdir(LIB)):
		print(f)


if __name__ == '__main__':
	main()
