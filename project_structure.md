# Project Structure — heavymetal

Generated: 20250903_175515

````
.
├── backend
│   ├── app.py.bak
│   ├── config.py
│   ├── errors.py
│   ├── extensions.py
│   ├── __init__.py
│   ├── logs
│   │   └── app.log
│   ├── models.py
│   ├── routes
│   │   ├── dashboards.py
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── sessions.py
│   │   └── workouts.py
│   └── security.py
├── bin
│   └── tailwindcss
├── docs
│   ├── executive_summary
│   │   ├── ._00_audit_highlights.md
│   │   ├── 00_audit_highlights.md
│   │   ├── ._01_charts_and_assets.md
│   │   ├── 01_charts_and_assets.md
│   │   ├── ._02_favicons_and_manifest.md
│   │   ├── 02_favicons_and_manifest.md
│   │   ├── ._03_flask_hardening.md
│   │   ├── 03_flask_hardening.md
│   │   ├── ._04_dependencies_and_requirements.md
│   │   ├── 04_dependencies_and_requirements.md
│   │   ├── ._05_project_clean_pack.md
│   │   ├── 05_project_clean_pack.md
│   │   ├── ._06_ci_cd_precommit.md
│   │   ├── 06_ci_cd_precommit.md
│   │   ├── ._07_alembic_and_seed.md
│   │   ├── 07_alembic_and_seed.md
│   │   ├── ._08_docker_dev_env.md
│   │   ├── 08_docker_dev_env.md
│   │   ├── ._09_readme_polish.md
│   │   ├── 09_readme_polish.md
│   │   ├── ._10_error_pages.md
│   │   ├── 10_error_pages.md
│   │   ├── ._11_cache_busting.md
│   │   ├── 11_cache_busting.md
│   │   ├── ._12_accessibility_and_meta.md
│   │   ├── 12_accessibility_and_meta.md
│   │   ├── ._13_filename_header_rule.md
│   │   ├── 13_filename_header_rule.md
│   │   ├── ._executive_summary.md
│   │   ├── executive_summary.md
│   │   ├── ._executive_summary.pdf
│   │   └── executive_summary.pdf
│   ├── rebuild_venv.sh
│   └── requirements_workflow.md
├── frontend
│   ├── static
│   │   ├── apple-touch-icon.png
│   │   ├── favicon-16x16.png
│   │   ├── favicon-32x32.png
│   │   ├── favicon.ico
│   │   ├── js
│   │   │   ├── card-sparks-rocket.js
│   │   │   └── charts-init-rocket.js
│   │   ├── output.css
│   │   ├── rocket
│   │   │   ├── assets
│   │   │   │   ├── charts.js
│   │   │   │   ├── constants.js
│   │   │   │   ├── dark-mode.js
│   │   │   │   ├── index.js
│   │   │   │   ├── sidebar.js
│   │   │   │   └── style.css
│   │   │   └── dist
│   │   │       ├── css
│   │   │       │   └── output.css
│   │   │       ├── main.bundle.js
│   │   │       └── main.css
│   │   ├── safari-pinned-tab.svg
│   │   ├── site.webmanifest
│   │   └── style.css
│   └── templates
│       ├── base.html
│       ├── dashboards
│       │   ├── _cards.html
│       │   ├── _cards_svg.html
│       │   ├── _charts.html
│       │   └── index.html
│       ├── errors
│       │   ├── 404.html
│       │   └── 500.html
│       ├── main
│       │   └── home.html
│       ├── sessions
│       │   ├── detail.html
│       │   └── list.html
│       └── workouts
│           ├── detail.html
│           └── list.html
├── .gitignore
├── migrations
│   ├── alembic.ini
│   ├── env.py
│   ├── README
│   ├── script.py.mako
│   └── versions
│       └── 52d889bcec91_baseline_models.py
├── mypy.ini
├── package.json
├── package-lock.json
├── .pre-commit-config.yaml
├── project_clean_pack.sh
├── project_structure.md
├── requirements.in
├── requirements.txt
├── run.py
└── tools
    └── ensure_filename_header.py

23 directories, 95 files
````
