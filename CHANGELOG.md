## [0.4.0] - 2026-10-27

### 🚀 Features

- Update database credentials handling and OpenBao integration in connectors

### ⚙️ Miscellaneous Tasks

- Update copier template to v2.0.0
- *(renovate)* Record the copier template's full git URL
- Update copier template to v2.1.0
## [0.3.1] - 2026-10-17

### 🐛 Bug Fixes

- Update Python version requirements and adjust CI configuration
## [0.3.0] - 2026-10-17

### 🚀 Features

- Add ClusterDBConnector for in-pod OpenBao credentials
- Add ClusterAdminDBConnector for in-pod superuser credentials

### 🐛 Bug Fixes

- Update source path format in .copier-answers.yml
- Load kubeconfig per connector and tighten connector error handling

### 📚 Documentation

- Update README and tests to reflect changes in credential management from VSO to External Operator
- Document ClusterDBConnector
- Document ClusterAdminDBConnector
- Document connector policy attributes and db_query sources

### ⚙️ Miscellaneous Tasks

- Update version in .copier-answers.yml and release workflow, adjust changelog generation logic
- Update commit version to v1.7.2 in .copier-answers.yml and initialize git with main branch in justfile
- *(deps)* Bump kubernetes to 37 and replace asserts with raises
- Turn connector comment plan into tests
- Remove empty features package left from the template
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
