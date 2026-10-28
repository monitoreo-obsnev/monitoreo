"""Plugin class: a toolbar button and a Web menu entry that show the MonitorEO panel."""

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from . import deps

HERE = os.path.dirname(os.path.abspath(__file__))


class MonitorEOPlugin:

	def __init__(self, iface):
		self.iface = iface
		self.action = None
		self.dock = None

	def initGui(self):
		self.action = QAction(QIcon(os.path.join(HERE, 'icon.png')), 'MonitorEO', self.iface.mainWindow())
		self.action.setCheckable(True)
		self.action.setToolTip('MonitorEO: series temporales y mapas de Google Earth Engine')
		self.action.triggered.connect(self.toggle)
		self.iface.addToolBarIcon(self.action)
		self.iface.addPluginToWebMenu('MonitorEO', self.action)

	def unload(self):
		if self.dock:
			self.dock.stop()
			self.iface.removeDockWidget(self.dock)
			self.dock.deleteLater()
			self.dock = None
		self.iface.removePluginWebMenu('MonitorEO', self.action)
		self.iface.removeToolBarIcon(self.action)

	def toggle(self, checked):
		if self.dock is None:
			problem = deps.missing()
			if problem:
				from qgis.PyQt.QtWidgets import QMessageBox
				QMessageBox.critical(self.iface.mainWindow(), 'MonitorEO',
				                     f'Faltan librerías del plugin ({problem}). Instala el plugin desde su zip completo.')
				self.action.setChecked(False)
				return
			from .dock import MonitorEODock
			self.dock = MonitorEODock(self.iface)
			self.dock.visibilityChanged.connect(self.action.setChecked)
			self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
		self.dock.setVisible(checked)
