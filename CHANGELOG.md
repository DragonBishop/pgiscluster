## [0.4.0](https://github.com/DragonBishop/pgiscluster/compare/v0.3.1...v0.4.0) - 2026-11-05

### 🚀 Features

- Update database credentials handling and OpenBao integration in connectors ([c3bfde6](https://github.com/DragonBishop/pgiscluster/commit/c3bfde6b3e9ae37ee309e64de232bd5216878d63))

### ⚙️ Miscellaneous Tasks

- Update copier template to v2.0.0 ([5d62969](https://github.com/DragonBishop/pgiscluster/commit/5d629697a424af7db04ffbf5b0c911ce3b8ac4c8))
- *(renovate)* Record the copier template's full git URL ([ffba278](https://github.com/DragonBishop/pgiscluster/commit/ffba278b3d772efcc325115cb91dda1df9cf9f6d))
- Update copier template to v2.1.0 ([c49d3cd](https://github.com/DragonBishop/pgiscluster/commit/c49d3cd77663801f66ab3fd50800a58695d29eb4))
- Update dependencies and GitHub Actions versions by updating template to v. 2.3.0 ([10d6dea](https://github.com/DragonBishop/pgiscluster/commit/10d6deafb8f39c523ced4bb3859b3c8cb3e1f84f))

## [0.3.1](https://github.com/DragonBishop/pgiscluster/compare/v0.3.0...v0.3.1) - 2026-10-17

### 🐛 Bug Fixes

- Update Python version requirements and adjust CI configuration ([f10b07a](https://github.com/DragonBishop/pgiscluster/commit/f10b07a538ba26860400482160632dd48f305a43))

## [0.3.0](https://github.com/DragonBishop/pgiscluster/compare/v0.2.0...v0.3.0) - 2026-10-17

### 🚀 Features

- Add ClusterDBConnector for in-pod OpenBao credentials ([13cf2b2](https://github.com/DragonBishop/pgiscluster/commit/13cf2b2a1c67cb0bc7359fa01f43db8d2842fd80))
- Add ClusterAdminDBConnector for in-pod superuser credentials ([20c34e6](https://github.com/DragonBishop/pgiscluster/commit/20c34e6109111521c7246a54fa953fc5fd97ebb8))

### 🐛 Bug Fixes

- Update source path format in .copier-answers.yml ([363c874](https://github.com/DragonBishop/pgiscluster/commit/363c874f6cd6e716d1939fbea0057a845aeb8a28))
- Load kubeconfig per connector and tighten connector error handling ([3a9a59a](https://github.com/DragonBishop/pgiscluster/commit/3a9a59a696e22ddbe9c30e84cfcf9b1de5f676af))

### 📚 Documentation

- Update README and tests to reflect changes in credential management from VSO to External Operator ([ba16a17](https://github.com/DragonBishop/pgiscluster/commit/ba16a17e00a0ec0d3c5e370812fcc3dd79db2ab6))
- Document ClusterDBConnector ([fdfbf07](https://github.com/DragonBishop/pgiscluster/commit/fdfbf075e5ece6753cd70d3ea71c8dc8d130dbae))
- Document ClusterAdminDBConnector ([67a7a0c](https://github.com/DragonBishop/pgiscluster/commit/67a7a0c10eb0e55e0242e2e28b7abd7d74a99547))
- Document connector policy attributes and db_query sources ([a4907f3](https://github.com/DragonBishop/pgiscluster/commit/a4907f33647ae6c88b429ec8de9bf78f68951a5f))

### ⚙️ Miscellaneous Tasks

- Update version in .copier-answers.yml and release workflow, adjust changelog generation logic ([b3170c9](https://github.com/DragonBishop/pgiscluster/commit/b3170c9e6b87e2e1bb43313cebc3ce9a60d6735e))
- Update commit version to v1.7.2 in .copier-answers.yml and initialize git with main branch in justfile ([109ff62](https://github.com/DragonBishop/pgiscluster/commit/109ff623868127c180df635d76c9a21a96a8bd49))
- *(deps)* Bump kubernetes to 37 and replace asserts with raises ([e142f40](https://github.com/DragonBishop/pgiscluster/commit/e142f40737322d6fc66f22e0b94536f6d01170ba))
- Turn connector comment plan into tests ([6775c79](https://github.com/DragonBishop/pgiscluster/commit/6775c79427104ca261becb337261fac5d255285d))
- Remove empty features package left from the template ([db1a59a](https://github.com/DragonBishop/pgiscluster/commit/db1a59ac86fed10b3dd05f3e6793811cd49e7961))

## [0.2.0](https://github.com/DragonBishop/pgiscluster/releases/tag/v0.2.0) - 2026-09-17

### 🚀 Features

- Initialize project via copier template (uv, pytest, CI, notebooks) ([af5469c](https://github.com/DragonBishop/pgiscluster/commit/af5469c8d63cfd6e77fdf920d3800a1da2b280f4))
- Update dependencies and configurations across multiple components ([51e42d9](https://github.com/DragonBishop/pgiscluster/commit/51e42d91908444ae48fcb50fee4f088bf629827f))
- *(connector)* Implement DBConnector._get_target CiliumLocalRedirectPolicy lookup ([5c51b46](https://github.com/DragonBishop/pgiscluster/commit/5c51b46ad49b2630e34991a597f9cf090e0c0722))
- *(connector)* Add HostDBConnector and HostAdminDBConnector, file-based db_query, pluggable target resolver ([2556cd4](https://github.com/DragonBishop/pgiscluster/commit/2556cd450ce50e745953ca57032b7e8d4c82ab50))
- Prepare pgiscluster for publication ([cc2e1b9](https://github.com/DragonBishop/pgiscluster/commit/cc2e1b9593042afcb230f74f1c4e11ee4eade194))
- Add dependencies and pyproject.toml metadata ([a06394c](https://github.com/DragonBishop/pgiscluster/commit/a06394c0ac37325e77b3a6dae1cb518e92c9617d))

### 📚 Documentation

- Move package README to repo root, fix repo links ([6c2420c](https://github.com/DragonBishop/pgiscluster/commit/6c2420c034aa5eb8a4623bd8cf8a6c282aacdff7))

### ⚙️ Miscellaneous Tasks

- Rename package to pgiscluster and prune unused dependencies ([b7eb4e0](https://github.com/DragonBishop/pgiscluster/commit/b7eb4e049d6341f62eac166e21f37215ffe7da0d))
- Scaffold repo from python-copier-template-ds ([e5a42fe](https://github.com/DragonBishop/pgiscluster/commit/e5a42fe8c3cf21a4a38056972719db332fa2d828))

