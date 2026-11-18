"""The log of the plugin and its window "Send the logs".

The plugin writes qgis.log in the folder MonitorEO of the user (monitoreo.logs): each task with its end, and each error
of the message bar, with the traceback of the tasks that failed. "Send the logs" (the button next to each error of the
message bar and the entry of the menu "Suggest a change or report an error") opens LogsDialog: the newest lines of that
log, without what would say who the user is (monitoreo.logs.collect), which the user reads and may change, and what
they write of the error; Send posts them to the anonymous form of the team in a QGIS task."""

import traceback

from qgis.core import Qgis, QgsApplication, QgsTask
from qgis.PyQt.QtGui import QFontDatabase
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout

from monitoreo import __version__, about, logs

LOG = 'qgis.log'  # in logs.folder(): ~/MonitorEO, or the folder of MONITOREO_OUTPUT


def write(entry):
	"""Add ENTRY (a dict) to the log of the plugin; it never fails."""
	logs.write(logs.path(LOG), entry)


def write_failure(task, exception):
	"""Add to the log that the task TASK (its description) failed with EXCEPTION, with its traceback."""
	write({'task': task, 'failed': f'{type(exception).__name__}: {exception}',
	       'traceback': ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))})


def qgis_version():
	try:
		return Qgis.version()
	except AttributeError:  # QGIS before 3.12
		return getattr(Qgis, 'QGIS_VERSION', '?')


def logs_text(plugin, project=''):
	"""What "Send the logs" shows: the newest lines of the log of the plugin (version PLUGIN), with the versions of
	QGIS and of the package, without the project of Earth Engine PROJECT of the user (see monitoreo.logs.collect)."""
	project = (project or '').strip()
	return logs.collect('qgis', plugin, hide=[project] if project else (),
	                    extra={'QGIS': qgis_version(),
	                           'Earth Engine': 'a project of the user' if project else 'the shared account of MonitorEO'})


class LogsDialog(QDialog):
	"""The window "Send the logs": what the user wrote of the error (ERROR, the message that failed, to start with),
	and the logs (logs_text), which the user may change. Send posts them in a task (kept by the window while it runs)
	and calls ON_SENT(text) if the form took them; else the window says why, and stays open."""

	def __init__(self, parent, plugin, project='', error='', on_sent=None):
		super().__init__(parent)
		texts = about.LOGS['en']
		self.plugin, self.on_sent, self.tasks = plugin, on_sent, []
		self.setWindowTitle(f"MonitorEO: {texts['button'].lower()}")
		self.resize(780, 600)
		lay = QVBoxLayout(self)
		help_label = QLabel(texts['help'])
		help_label.setWordWrap(True)
		lay.addWidget(help_label)
		lay.addWidget(QLabel(texts['description']))
		self.description = QPlainTextEdit(f'The error: {error}\n' if error else '')
		self.description.setMaximumHeight(90)
		lay.addWidget(self.description)
		lay.addWidget(QLabel('Logs'))
		self.logs = QPlainTextEdit(logs_text(plugin, project))
		self.logs.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
		self.logs.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
		lay.addWidget(self.logs, 1)
		self.status = QLabel('')
		self.status.setWordWrap(True)
		lay.addWidget(self.status)
		buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
		self.send_button = buttons.addButton('Send', QDialogButtonBox.ButtonRole.ActionRole)
		self.send_button.clicked.connect(lambda checked=False: self.send())
		buttons.rejected.connect(self.reject)
		lay.addWidget(buttons)

	def send(self):
		text, description = self.logs.toPlainText(), self.description.toPlainText()
		if not text.strip():
			self.status.setText('There are no logs to send.')
			return
		self.send_button.setEnabled(False)
		self.status.setText('Sending…')
		version = f'{self.plugin} (monitoreo {__version__})'

		def run(task):
			logs.send(text, 'qgis', version, description)
			return True

		def finished(exception, result=None):
			if task in self.tasks:
				self.tasks.remove(task)
			if exception is not None:
				self.status.setText(str(exception))
				self.send_button.setEnabled(True)
				return
			self.accept()
			if self.on_sent:
				self.on_sent(about.LOGS['en']['sent'])

		task = QgsTask.fromFunction('Send the logs of MonitorEO', run, on_finished=finished)
		self.tasks.append(task)
		QgsApplication.taskManager().addTask(task)
