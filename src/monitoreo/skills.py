"""The recipes of MonitorEO as skills (the folders of recipes/, each with its SKILL.md in the format of Agent Skills): how
to repeat or adapt the case studies done with MonitorEO (the disturbances of the EVEREST national parks...) and the
method they followed. The MCP server serves them with the extension Skills of MCP (io.modelcontextprotocol/skills,
SEP-2640: skills/list, skills/get, and their files as resources skill://monitoreo/<name>/<file>, each with its size
and its sha256 digest), and, for the clients without it, with the tool recipes.

A skill is a folder of recipes/ whose SKILL.md begins with a YAML frontmatter with at least name (the name of the
folder: lowercase letters, digits and hyphens, at most 64 characters) and description (at most 1024 characters).

References:
    MCP Skills extension (SEP-2640): https://modelcontextprotocol.io/extensions/skills/overview
    Agent Skills: https://agentskills.io
"""

import hashlib
import os
import re

import yaml

FOLDER = os.path.join(os.path.dirname(__file__), 'recipes')
SCHEME = 'skill://monitoreo/'
EXTENSION = 'io.modelcontextprotocol/skills'
NAME = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
MAX_NAME, MAX_DESCRIPTION = 64, 1024
MAX_FILES, MAX_BYTES = 512, 16 * 2 ** 20  # the limits of a skill in the extension
TTL_MS = 3600 * 1000  # the clients may keep the list an hour: the recipes change with the package
MIME = {'.md': 'text/markdown', '.json': 'application/json', '.csv': 'text/csv', '.txt': 'text/plain',
        '.yaml': 'application/yaml', '.yml': 'application/yaml', '.py': 'text/x-python', '.R': 'text/x-r'}


def frontmatter(text):
	"""The YAML frontmatter of the text of a SKILL.md (a dict), or ValueError."""
	m = re.match(r'^---\r?\n(.*?)\r?\n---\r?\n', text, re.S)
	if not m:
		raise ValueError('a SKILL.md begins with its frontmatter between two lines ---')
	data = yaml.safe_load(m.group(1))
	if not isinstance(data, dict):
		raise ValueError('the frontmatter of a SKILL.md is a YAML mapping')
	return data


def check(name, meta):
	"""Check the frontmatter META of the skill of the folder NAME; ValueError otherwise."""
	if meta.get('name') != name:
		raise ValueError(f'the name of the skill {name} ({meta.get("name")!r}) must be that of its folder')
	if len(name) > MAX_NAME or not NAME.match(name):
		raise ValueError(f'{name}: a name of lowercase letters, digits and single hyphens, at most {MAX_NAME} '
		                 'characters')
	description = meta.get('description')
	if not isinstance(description, str) or not description.strip() or len(description) > MAX_DESCRIPTION:
		raise ValueError(f'{name}: a description of 1 to {MAX_DESCRIPTION} characters')


def _files(folder):
	out = []
	for root, dirs, files in os.walk(folder):
		dirs[:] = sorted(d for d in dirs if not d.startswith(('.', '__')))
		for f in sorted(files):
			if not f.startswith('.') and not os.path.islink(os.path.join(root, f)):  # a link may point outside
				out.append(os.path.relpath(os.path.join(root, f), folder).replace(os.sep, '/'))
	return out


def names(folder=FOLDER):
	"""The names of the skills of FOLDER: its folders with a SKILL.md."""
	if not os.path.isdir(folder):
		return []
	return sorted(d for d in os.listdir(folder) if os.path.isfile(os.path.join(folder, d, 'SKILL.md')))


def entry(name, folder=FOLDER):
	"""The entry of the skill NAME as skills/list and skills/get give it: {uri, frontmatter, resources: [{uri, digest,
	size}]}, the digests and sizes of the bytes served (see read)."""
	path = os.path.join(folder, name)
	with open(os.path.join(path, 'SKILL.md'), encoding='utf-8') as f:
		meta = frontmatter(f.read())
	check(name, meta)
	resources, total = [], 0
	for rel in _files(path):
		with open(os.path.join(path, rel), 'rb') as f:
			data = f.read()
		total += len(data)
		resources.append({'uri': f'{SCHEME}{name}/{rel}', 'digest': 'sha256:' + hashlib.sha256(data).hexdigest(),
		                  'size': len(data)})
	if len(resources) > MAX_FILES or total > MAX_BYTES:
		raise ValueError(f'{name}: more than {MAX_FILES} files or {MAX_BYTES} bytes')
	return {'uri': f'{SCHEME}{name}/SKILL.md', 'frontmatter': meta, 'resources': resources}


def entries(folder=FOLDER, skipped=None):
	"""The entries of the skills of FOLDER (see entry); a skill that cannot be read is left out (with SKIPPED, a list,
	its name and why are added to it), so that one bad recipe does not hide the others."""
	out = []
	for n in names(folder):
		try:
			out.append(entry(n, folder))
		except (ValueError, OSError, yaml.YAMLError) as e:
			if skipped is not None:
				skipped.append((n, str(e)))
	return out


def locate(uri, folder=FOLDER):
	"""(name, relative path, absolute path) of the file of a skill of URI (skill://monitoreo/<name>/<file>), or
	ValueError: an unknown URI, or one outside the folder of its skill."""
	if not isinstance(uri, str) or not uri.startswith(SCHEME):
		raise ValueError(f'unknown skill resource {uri!r}: the skills of MonitorEO are {SCHEME}<name>/SKILL.md')
	name, _, rel = uri[len(SCHEME):].partition('/')
	if name not in names(folder) or not rel:
		raise ValueError(f'unknown skill resource {uri!r}')
	base = os.path.realpath(os.path.join(folder, name))
	path = os.path.realpath(os.path.join(base, rel))
	if not path.startswith(base + os.sep) or not os.path.isfile(path):
		raise ValueError(f'unknown skill resource {uri!r}')
	return name, rel, path


def read(uri, folder=FOLDER):
	"""(text, MIME type) of the file of a skill at URI (see locate)."""
	_, rel, path = locate(uri, folder)
	with open(path, 'rb') as f:
		data = f.read()
	try:
		text = data.decode('utf-8')
	except UnicodeDecodeError:
		raise OSError(f'{uri} is not a text file in UTF-8') from None
	return text, MIME.get(os.path.splitext(rel)[1], 'text/plain')


def get(uri, folder=FOLDER):
	"""The entry of the skill whose SKILL.md is at URI (see entry), or ValueError."""
	name, rel, _ = locate(uri, folder)
	if rel != 'SKILL.md':
		raise ValueError(f'{uri!r} is not the SKILL.md of a skill: {SCHEME}{name}/SKILL.md')
	return entry(name, folder)


def catalog(folder=FOLDER):
	"""The skills of FOLDER for the tool recipes: [{name, description, uri, metadata}]."""
	return [{'name': e['frontmatter']['name'], 'description': e['frontmatter']['description'], 'uri': e['uri'],
	         'metadata': e['frontmatter'].get('metadata') or {}} for e in entries(folder)]


def extension():
	"""The extension Skills of MCP for an MCPServer of mcp 2 (mcp.server.extension), or None with mcp 1.x, which has
	no extensions (the tool recipes and the resources serve them there)."""
	try:
		from mcp.server.extension import Extension, MethodBinding, ResourceBinding
		from mcp.server.mcpserver.resources import TextResource
		from mcp.shared.exceptions import MCPError
		from mcp_types import INVALID_PARAMS, PaginatedRequestParams, RequestParams
	except ImportError:
		return None

	class GetParams(RequestParams):
		uri: str

	skipped = []
	snapshot = {}  # the entries and the texts of the skills when the server starts: what it lists and what it serves
	for e in entries(skipped=skipped):
		try:
			texts = {r['uri']: read(r['uri']) for r in e['resources']}
		except (ValueError, OSError) as err:
			skipped.append((e['frontmatter']['name'], str(err)))
			continue
		snapshot[e['uri']] = (e, texts)
	for name, why in skipped:
		import sys
		print(f'MonitorEO: the recipe {name} is not served: {why}', file=sys.stderr)

	def _result(**kw):
		return dict(resultType='complete', ttlMs=TTL_MS, cacheScope='public', **kw)

	async def list_skills(ctx, params):
		return _result(skills=[e for e, _ in snapshot.values()])

	async def get_skill(ctx, params):
		if params.uri not in snapshot:
			raise MCPError(code=INVALID_PARAMS, message=f'unknown skill {params.uri!r}: the skills of MonitorEO are '
			                                          f'{SCHEME}<name>/SKILL.md (skills/list)')
		return _result(skill=snapshot[params.uri][0])

	class Skills(Extension):
		identifier = EXTENSION

		def resources(self):
			out = []
			for uri, (e, texts) in snapshot.items():
				for r_uri, (text, mime) in texts.items():
					main = r_uri == uri
					out.append(ResourceBinding(resource=TextResource(
						uri=r_uri, name=e['frontmatter']['name'] if main else r_uri[len(SCHEME):], mime_type=mime,
						text=text, description=e['frontmatter']['description'] if main else None)))
			return out

		def methods(self):
			return (MethodBinding('skills/list', PaginatedRequestParams, list_skills),
			        MethodBinding('skills/get', GetParams, get_skill))

	return Skills()
