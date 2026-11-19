"""numpy with MKL in one thread (MKL_THREADING_LAYER=SEQUENTIAL), set by monitoreo before numpy computes: on Windows,
MKL with the OpenMP of LLVM of conda-forge ended the process at the first product of matrices, so every chart (and every
time series of the assistant) stopped its MCP server ("Windows fatal exception: code 0xc06d007f", 2026-11-19)."""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(code, **env):
	environ = {k: v for k, v in os.environ.items() if k != 'MKL_THREADING_LAYER'}
	environ.update(PYTHONPATH=os.path.join(ROOT, 'src'), **env)
	return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=environ, timeout=120)


def test_monitoreo_sets_mkl_in_one_thread_before_numpy():
	"""Importing monitoreo (as the MCP server, the assistant and the command line do first) sets it, before numpy is
	imported; a product of matrices and a chart then work."""
	run = _run("import sys, os, monitoreo; print(os.environ['MKL_THREADING_LAYER'], 'numpy' in sys.modules)")
	assert run.returncode == 0 and run.stdout.split() == ['SEQUENTIAL', 'False'], run.stderr
	run = _run("import monitoreo, numpy as np; a = np.ones((3, 3)); print((a @ a).sum())")
	assert run.returncode == 0 and run.stdout.strip() == '27.0', run.stderr


def test_a_value_of_the_user_is_kept():
	run = _run("import os, monitoreo; print(os.environ['MKL_THREADING_LAYER'])", MKL_THREADING_LAYER='TBB')
	assert run.returncode == 0 and run.stdout.strip() == 'TBB', run.stderr
