"""The recipes of MonitorEO as skills (monitoreo.skills) and their serving by the MCP server with the extension Skills of
MCP (io.modelcontextprotocol/skills): every recipe valid (name, description, files, digests), no path of a computer in
them, unknown or outside URIs refused, the tool recipes, the command line, and, with mcp 2, skills/list, skills/get and
resources/read through an MCP client."""

import asyncio
import hashlib
import os
import re

import pytest

from monitoreo import cli, mcp_server, skills  # imported here: not while capsys captures stderr (mcp keeps it)


def test_every_recipe_is_a_valid_skill():
	names = skills.names()
	assert 'monitoreo-disturbance-case-study' in names and len([n for n in names if n.startswith('everest-')]) >= 8
	for e in skills.entries():
		meta = e['frontmatter']
		assert e['uri'] == f"skill://monitoreo/{meta['name']}/SKILL.md"
		assert skills.NAME.match(meta['name']) and len(meta['description']) <= skills.MAX_DESCRIPTION
		assert e['resources'][0]['uri'] == e['uri'] or any(r['uri'] == e['uri'] for r in e['resources'])
		for r in e['resources']:
			path = os.path.join(skills.FOLDER, r['uri'][len(skills.SCHEME):])
			with open(path, 'rb') as f:  # the bytes on disk, not those of skills.read
				data = f.read()
			assert r['digest'] == 'sha256:' + hashlib.sha256(data).hexdigest() and r['size'] == len(data)
			text = data.decode('utf-8')
			# the recipes go to every user: no path of the computer where they were written
			assert not re.search(r'/Users/|/home/|[A-Za-z]:\\Users', text), r['uri']
			if meta['name'].startswith('everest-') and r['uri'] == e['uri']:  # how to rebuild the files of <everest>
				assert '<everest>' not in text or '**Files of this recipe.**' in text


def test_a_bad_recipe_does_not_hide_the_others(tmp_path):
	for name, text in (('good', '---\nname: good\ndescription: x\n---\n# G\n'), ('bad', '# no frontmatter\n')):
		os.makedirs(tmp_path / name)
		(tmp_path / name / 'SKILL.md').write_text(text, encoding='utf-8')
	(tmp_path / 'good' / 'link.md').symlink_to('/etc/hosts')  # links are not files of a skill
	skipped = []
	got = skills.entries(str(tmp_path), skipped)
	assert [e['frontmatter']['name'] for e in got] == ['good'] and skipped[0][0] == 'bad'
	assert [r['uri'] for r in got[0]['resources']] == ['skill://monitoreo/good/SKILL.md']


def test_unknown_uris_and_bad_skills_are_refused(tmp_path):
	for uri in ('skill://monitoreo/nope/SKILL.md', 'skill://other/x/SKILL.md', 'file:///etc/passwd',
	            'skill://monitoreo/monitoreo-disturbance-case-study/../../catalog.json',
	            'skill://monitoreo/monitoreo-disturbance-case-study/'):
		with pytest.raises(ValueError, match='unknown skill resource'):
			skills.read(uri)
	with pytest.raises(ValueError, match='is not the SKILL.md'):
		os.makedirs(tmp_path / 'a-b')
		(tmp_path / 'a-b' / 'SKILL.md').write_text('---\nname: a-b\ndescription: x\n---\n# A\n', encoding='utf-8')
		(tmp_path / 'a-b' / 'notes.md').write_text('notes', encoding='utf-8')
		skills.get('skill://monitoreo/a-b/notes.md', str(tmp_path))
	assert skills.get('skill://monitoreo/a-b/SKILL.md', str(tmp_path))['frontmatter']['name'] == 'a-b'
	(tmp_path / 'a-b' / 'SKILL.md').write_text('---\nname: other\ndescription: x\n---\n', encoding='utf-8')
	with pytest.raises(ValueError, match='must be that of its folder'):
		skills.entry('a-b', str(tmp_path))
	(tmp_path / 'a-b' / 'SKILL.md').write_text('# no frontmatter\n', encoding='utf-8')
	with pytest.raises(ValueError, match='frontmatter'):
		skills.entry('a-b', str(tmp_path))


def test_the_tool_and_the_command_line(capsys):
	listed = mcp_server.recipes()
	assert 'everest-sierra-nevada-fire-2005' in listed and 'monitoreo-disturbance-case-study' in listed
	assert mcp_server.recipes('monitoreo-disturbance-case-study').startswith('---\nname: monitoreo-disturbance')
	with pytest.raises(Exception, match='unknown recipe'):
		mcp_server.recipes('nope')
	cli.main(['recipes'])
	assert 'everest-teide-fire-2023' in capsys.readouterr().out
	cli.main(['recipes', 'everest-teide-fire-2023'])
	assert capsys.readouterr().out.startswith('---\nname: everest-teide-fire-2023')


def test_skills_over_mcp():
	"""skills/list, skills/get and resources/read through an MCP client (mcp 2: its extensions)."""
	pytest.importorskip('mcp.server.extension')
	from mcp.client import Client

	async def run():
		async with Client(mcp_server.server) as c:
			assert skills.EXTENSION in (c.server_capabilities.extensions or {})
			raw = c.session._dispatcher.send_raw_request
			listed = await raw('skills/list', {}, {})
			assert listed['resultType'] == 'complete' and listed['cacheScope'] == 'public' and listed['ttlMs'] > 0
			assert {s['frontmatter']['name'] for s in listed['skills']} == set(skills.names())
			first = listed['skills'][0]
			got = await raw('skills/get', {'uri': first['uri']}, {})
			assert got['skill'] == first
			text = (await c.read_resource(first['uri'])).contents[0].text
			assert 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest() == first['resources'][0]['digest']
			with pytest.raises(Exception, match='unknown skill') as err:
				await raw('skills/get', {'uri': 'skill://monitoreo/nope/SKILL.md'}, {})
			assert getattr(err.value, 'code', None) in (None, -32602)
			for r in first['resources'][1:]:  # every file served as listed
				t = (await c.read_resource(r['uri'])).contents[0].text
				assert 'sha256:' + hashlib.sha256(t.encode('utf-8')).hexdigest() == r['digest']
	asyncio.run(run())
