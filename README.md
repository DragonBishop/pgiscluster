# pgiscluster

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/DragonBishop/pgiscluster/blob/main/LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/downloads/)

Python classes for connecting to and querying a PostGIS database, with credentials resolved dynamically at runtime.

**Status: Alpha.** `HostDBConnector` connects from a workstation and `ClusterDBConnector` connects from inside a pod. Their default addresses and credential sources assume specific cluster infrastructure, but all of them are plain, overridable class attributes and methods. This package is a prototype. Its successor, Cluster Connect, will replace it.

## Key features

- Fetches credentials on every connection, from a Kubernetes Secret (`HostDBConnector`) or straight from OpenBao or Vault (`ClusterDBConnector`), so rotation is picked up automatically.
- Resolves the database address live from the cluster.
- Query results returned as GeoDataFrames for downstream GIS/analytics work.

## Install

```bash
pip install pgiscluster
```

## Requirements

- Python >= 3.14.7
- A `kubectl` context with:
  - Cluster-scoped read access to CustomResourceDefinitions and their custom objects, for address discovery.
  - Read access to Secrets in the namespace holding the database credentials.
- A reachable host:port for the database. By default, resolved via a Cilium `CiliumLocalRedirectPolicy` labeled `app.kubernetes.io/name=postgis-cluster`.
- A Kubernetes Secret with base64-encoded `username`/`password` keys for the database login.
- See [Configuration](#configuration) for alternatives to defaults.

## Usage

```python
from pgiscluster import HostDBConnector

connector = HostDBConnector()
df = connector.db_query(
    "queries/nearby.sql", geom_col="geom"
)  # from a .sql file (default)
df = connector.db_query(query="SELECT * FROM my_table", geom_col="geom")  # literal SQL
```

`HostDBConnector` resolves the database host/port at construction, then fetches a fresh username/password pair on every connection attempt.

### Configuration

#### `HostDBConnector`

`HostDBConnector(database="data_science", target_resolver=None)`: `database` is the target database name, defaulting to `"data_science"`.

By default, `HostDBConnector` resolves host/port from the cluster's `CiliumLocalRedirectPolicy`, reading the address from its `spec.redirectFrontend.addressMatcher`. For a different mechanism (a NodePort/LoadBalancer Service, a port-forward, a socat proxy), override `_get_target` in a subclass to reuse the same logic across many instances, or pass `target_resolver`, a zero-argument callable returning `(host, port)`, for a one-off:

```python
connector = HostDBConnector(target_resolver=lambda: ("localhost", 5432))
```

Credentials come from a Kubernetes Secret. Its name and namespace are set by the class attributes `HostDBConnector.SECRET_NAME` and `HostDBConnector.SECRET_NAMESPACE`. You can override them to point elsewhere. The reference cluster populates that Secret with External Secrets Operator, syncing a dynamically-generated OpenBao database credential. However, any mechanism works as long as the Secret has `username`/`password` keys.

`db_query(query_file=None, *, query=None, geom_col)` runs a SQL query and returns a [GeoDataFrame](https://geopandas.org/), decoding one geometry column per call. One of either `query_file` (a path to a `.sql` file, the default), or `query`, a literal SQL string.

#### `HostAdminDBConnector`

A `HostDBConnector` subclass that reads the cluster's Postgres **superuser** credential from a static secret, instead of the scoped `app_readwrite` dynamic lease, for schema/DDL changes:

```python
from pgiscluster import HostAdminDBConnector

connector = HostAdminDBConnector()
```

#### `ClusterDBConnector`

For code running inside the cluster, such as Prefect flow-run Jobs. On every new connection it logs in to OpenBao (or Vault) with Kubernetes auth, then generates a fresh database login from `database/creds/<DATABASE_ROLE>`. It needs no kubeconfig and no read access to Secrets.

The class attributes:

| Attribute | Default | Meaning |
| :--- | :--- | :--- |
| `AUTH_ROLE` | `None` (required) | The OpenBao Kubernetes auth role the pod logs in as |
| `DATABASE_ROLE` | `"postgis-app-role"` | The database secrets engine role to read |
| `TOKEN_PATH` | `"/var/run/secrets/openbao/token"` | The projected service account token to log in with |
| `HOST`, `PORT` | `"postgis-cluster-rw.databases.svc.cluster.local"`, `5432` | The in-cluster read-write Service |

`AUTH_ROLE` has no default, because each app logs in with its own role. Set it in a subclass:

```python
from pgiscluster import ClusterDBConnector


class EtlDB(ClusterDBConnector):
    AUTH_ROLE = "etl-role"


connector = EtlDB(database="etl")
```

The server address comes from `BAO_ADDR`, then `VAULT_ADDR`, and its CA file from `BAO_CACERT`, then `VAULT_CACERT`. With no CA file set, the system CAs are used. Postgres TLS follows libpq's own `PGSSLMODE` and `PGSSLROOTCERT` variables.

The pod needs:

- an OpenBao Kubernetes auth role bound to its service account, with a policy that can `read` `database/creds/<DATABASE_ROLE>`;
- a projected token for the audience the auth role checks, mounted at `TOKEN_PATH`;
- a network policy allowing egress to OpenBao on 8200 and to Postgres on 5432.

```yaml
volumes:
  - name: openbao-token
    projected:
      sources:
        - serviceAccountToken:
            audience: openbao
            expirationSeconds: 600
            path: token
containers:
  - volumeMounts:
      - {name: openbao-token, mountPath: /var/run/secrets/openbao, readOnly: true}
```

Each connection creates a new database login with its own lease. Leases are not revoked when connections close, so each one lasts until its TTL ends. Keep the role's TTL short.

## License

See [MIT LICENSE](https://github.com/DragonBishop/pgiscluster/blob/main/LICENSE).

## Links

- [Source](https://github.com/DragonBishop/pgiscluster)
- [Issues](https://github.com/DragonBishop/pgiscluster/issues)
- [Changelog](https://github.com/DragonBishop/pgiscluster/blob/main/CHANGELOG.md)

`pgiscluster` was originally developed inside the [Data Science Cluster](https://github.com/DragonBishop/data_science_cluster) repo, the reference cluster its defaults are built against. If you want to contribute, open a development branch and then submit a pull request.
