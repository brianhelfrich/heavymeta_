<!-- docs/requirements_workflow.md -->

# Requirements Management Workflow

A practical, reproducible way to manage Python dependencies for this project, with or without `pip-tools`.

> TL;DR: We pin exact versions in `requirements.txt` for reliability. We optionally keep a looser `requirements.in` and use `pip-tools` to regenerate pins when we choose to upgrade.

---

## 0) Prerequisites
- Python (see project’s supported version in `README`)
- `pip` and `venv` (or `pyenv`, optional)
- **Recommended**: [`pip-tools`](https://pypi.org/project/pip-tools/) for controlled upgrades

Directory assumptions:
```
project-root/
├─ venv/
├─ requirements.txt        # pinned, used by deploy/CI
├─ requirements.in         # optional, loose ranges for pip-tools
└─ docs/
   ├─ rebuild_venv.sh
   └─ requirements_workflow.md (this file)
```

---

## 1) Baseline: strict pins in `requirements.txt`
We deploy from **pinned** versions to guarantee reproducibility.

Create a fresh venv and install from pins:
```bash
rm -rf venv
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Freeze the currently-installed set (only when you intentionally change packages):
```bash
pip freeze > requirements.txt
```

> Note: Freezing overwrites any comments in `requirements.txt`. Keep notes in this doc or in commit messages.

---

## 2) (Optional but recommended) Use `pip-tools`
`pip-tools` lets us keep human-friendly constraints in `requirements.in` and compile a fully pinned `requirements.txt`.

Install tools (in a throwaway or tool venv):
```bash
pip install pip-tools
```

Create `requirements.in` with ranges you’re comfortable with, e.g.:
```txt
Flask>=3.1,<4.0
SQLAlchemy>=2.0,<3.0
psycopg2-binary>=2.9,<3.0
python-dotenv>=1.0
Jinja2>=3.1
Werkzeug>=3.1
click>=8.2
MarkupSafe>=3.0
blinker>=1.8
itsdangerous>=2.1
greenlet>=3.0
typing-extensions>=4.14
```

Compile pins:
```bash
pip-compile --generate-hashes --upgrade-package Flask --output-file requirements.txt requirements.in
# or simply
pip-compile --generate-hashes requirements.in
```

Apply exactly those pins to your venv:
```bash
pip-sync
```

> Use `--upgrade` or `--upgrade-package PKG` to selectively refresh.

---

## 3) Normal update cadence
When you decide to update dependencies:

**A) Quick path (no pip-tools):**
```bash
source venv/bin/activate
pip install --upgrade -r requirements.txt
pip check                     # verify dependency consistency
pytest -q || true             # run tests / smoke checks
pip freeze > requirements.txt # lock the new working set
```

**B) Controlled path (pip-tools):**
```bash
pip-compile --upgrade         # refresh pins to latest compatible
pip-sync                      # install exactly those versions
pip check
pytest -q || true
```

Commit with a clear message and include a short changelog (see §7).

---

## 4) Evaluating upgrades (what to take / avoid)

Discover what’s outdated:
```bash
pip list --outdated
# For a single package’s available versions:
pip index versions <package>
```

General guidance for this project stack:
- **Patch releases** (x.y.z) are usually safe to take quickly.
- **Minor releases** (x.y) are fine when changelogs look clean; run app smoke tests.
- **Major releases** (x) require reading changelogs/upgrade notes; plan a branch.
- **psycopg2-binary → psycopg3**: treat as a mini-migration; don’t switch casually.

Run a smoke test before freezing:
```bash
python -c "import flask, sqlalchemy; print(flask.__version__, sqlalchemy.__version__)"
```

---

## 5) Upgrading Python itself
Venvs are tied to the interpreter they were created with. On some distros, venv may symlink `/usr/bin/python3`, so your venv can appear to “float” with system upgrades. Regardless, safest practice after a Python upgrade is to rebuild the venv so wheels/extensions are compiled for the new ABI.

Use the helper script:
```bash
./docs/rebuild_venv.sh python3.13
```

Manual steps (if you prefer):
```bash
rm -rf venv
python3.13 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

---

## 6) CI/CD and production notes
- CI should always install from **`requirements.txt`** only.
- Consider `pip install --require-hashes -r requirements.txt` for supply-chain integrity if you compiled with `--generate-hashes`.
- Cache wheels between runs to speed up builds (`pip cache dir`).

---

## 7) Version control & documentation
When bumping deps, include in the commit message:
- Reason for the bump (security, bugfix, feature)
- Notable breaking changes addressed
- Links to release notes (paste URLs in the commit body)

Example commit subject:
```
Deps: upgrade Flask→3.1.2, typing-extensions→4.15.0; recompile pins
```

---

## 8) Troubleshooting
- **`pip check` reports conflicts** → Re-run `pip-compile` (if using pip-tools) or pin the conflicting transitive dep explicitly, then freeze.
- **Binary wheel errors (build fails)** → Ensure build deps are installed (e.g., `gcc`, `python3-devel`, `libpq-devel` for PostgreSQL bindings).
- **App breaks after upgrade** → Roll back by checking out the previous `requirements.txt` and `pip-sync` or reinstall.
- **Unexpected versions after install** → A stale venv or extra-editable installs can mask pins. Rebuild venv or run `pip list` to inspect.

---

## 9) Quick reference
```bash
# See outdated
pip list --outdated

# View versions for one package
pip index versions SQLAlchemy

# Freeze exact working set
pip freeze > requirements.txt

# pip-tools flow
pip-compile --generate-hashes requirements.in
pip-sync

# Rebuild venv (Python upgrade)
./docs/rebuild_venv.sh python3.13
```

---

*End of document.*
