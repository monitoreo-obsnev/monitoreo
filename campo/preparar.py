"""Copia a app/src/main/assets/www/lib lo que la app usa sin modificar:

  catalog.js y core.js   de ../monitoreo/gee (el mismo cálculo que la app de Earth Engine y el paquete de Python)
  ee_api_js.js           cliente JS de Earth Engine (@google/earthengine, la versión de gee/package.json)
  leaflet                mapa
  chart.umd.js           gráficos

    python preparar.py              solo catalog.js y core.js (tras actualizar el repositorio monitoreo)
    python preparar.py --npm DIR    también las librerías; DIR: carpeta con los paquetes de npm extraídos (npm pack + tar)

Ejecutarlo de nuevo tras actualizar el repositorio monitoreo (git pull) y antes de compilar el APK.
"""

import argparse
import glob
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
GEE = os.path.join(HERE, '..', 'monitoreo', 'gee')
LIB = os.path.join(HERE, 'app', 'src', 'main', 'assets', 'www', 'lib')


def one(pattern):
	found = sorted(glob.glob(pattern))
	if not found:
		raise SystemExit('no encuentro ' + pattern)
	return found[-1]


def main():
	p = argparse.ArgumentParser()
	p.add_argument('--npm')
	a = p.parse_args()
	os.makedirs(LIB, exist_ok=True)
	for name in ('catalog.js', 'core.js'):
		shutil.copy(os.path.join(GEE, name), LIB)
	if not a.npm:
		print('catalog.js y core.js copiados de', os.path.normpath(GEE))
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
