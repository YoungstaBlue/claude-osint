# Agent notes — claude-osint

Non-obvious things about working in this repository in the Base44 sandbox.

## What this repo is

A Claude Code skill pack: Markdown only. There is **no application, no package
manifest, no build step and no server** — the deliverables are `SKILL.md` files
under `.claude/skills/` (law & litigation pack), `skills/` (OSINT pack), plus
docs in `docs/`, `examples/` and `tests/`. The only executable code is
`skills/offensive-osint/scripts/{secret_scan,h1_reference}.py` (stdlib only) and
`.claude/hooks/prompt-refiner.py`.

So an update to this repository has nothing to "start": nothing in the tree
listens on a port. That is why the preview port showed a failed start.

## Running it here

One command from the repo root:

```bash
docker compose -f docker-compose.base44.yml up -d --build
```

`tools/preview/server.py` renders the repo's own Markdown (README, `docs/`,
`examples/`, `tests/`, every `SKILL.md`) on host port 3000, with a filterable
skill index. Source is bind-mounted and read per request, so edits appear on
reload; the page also polls `/__rev` and reloads itself when a Markdown file
changes. Nothing else needs installing — the container installs the `markdown`
renderer on startup. Editing the harness itself (CSS, routing in
`tools/preview/server.py`) needs `docker compose -f docker-compose.base44.yml
restart preview`; editing Markdown does not.

## Frontmatter must be valid YAML

Every `SKILL.md` begins with a `---` frontmatter block. A plain (unquoted)
`description:` value containing `: ` breaks the YAML parse and the file cannot
be loaded — that is exactly what took the law pack down. Quote any description
that contains a colon followed by a space:

```yaml
description: 'Builds 42 U.S.C. 1983 claims: color of state law, …'
```

Fast check for the whole pack (needs PyYAML):

```bash
docker run --rm -v "$PWD:/w" -w /w python:3.11-slim sh -c \
  'pip install -q pyyaml >/dev/null && python -c "
import glob,yaml
for f in glob.glob(\".claude/skills/*/SKILL.md\")+glob.glob(\"skills/*/SKILL.md\"):
    t=open(f).read(); i=t.find(\"---\",3); yaml.safe_load(t[3:i])
print(\"frontmatter OK\")"'
```

## CI

`.github/workflows/lint.yml` defines four jobs: markdownlint, SKILL.md YAML
frontmatter, `secret_scan.py` smoke test, shellcheck. Two things to know:

- `yaml-frontmatter` only validates `skills/*/SKILL.md`, not the law pack under
  `.claude/skills/`, so a broken law-skill frontmatter passes CI silently.
- The `markdown` job is **red and was red before the law pack landed**: `main`
  at `d8a4f83` already had 302 markdownlint errors, `e9b99448` has 1750 (the 100
  new skills add MD031/MD032/MD040 noise). It is not a startup blocker, but it
  is not a clean gate either.

Local equivalents: `npx markdownlint-cli2` for the markdown job, and
`python3 -m py_compile skills/offensive-osint/scripts/secret_scan.py`.
