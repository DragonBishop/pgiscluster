## [0.2.1] - 2026-10-08

### 🐛 Bug Fixes

- Update source path format in .copier-answers.yml

### 📚 Documentation

- Update README and tests to reflect changes in credential management from VSO to External Operator

### ⚙️ Miscellaneous Tasks

- Update version in .copier-answers.yml and release workflow, adjust changelog generation logic
- Update commit version to v1.7.2 in .copier-answers.yml and initialize git with main branch in justfile
## [0.2.0] - 2026-09-17

### 🚀 Features

- Initialize project via copier template (uv, pytest, CI, notebooks)
- Update dependencies and configurations across multiple components
- *(connector)* Implement DBConnector._get_target CiliumLocalRedirectPolicy lookup
- *(connector)* Add HostDBConnector and HostAdminDBConnector, file-based db_query, pluggable target resolver
- Prepare pgiscluster for publication
- Add dependencies and pyproject.toml metadata

### 📚 Documentation

- Move package README to repo root, fix repo links

### ⚙️ Miscellaneous Tasks

- Rename package to pgiscluster and prune unused dependencies
- Scaffold repo from python-copier-template-ds
