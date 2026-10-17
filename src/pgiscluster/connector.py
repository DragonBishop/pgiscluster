"""Connectors that resolve a PostGIS address and fresh credentials at runtime.

Each connector answers two questions, where is the database and who logs in,
through two methods its subclasses fill in:

    _get_target         -> (host, port), resolved once at construction
    _get_credentials    -> (username, password), fetched on every new connection

                        _get_target                  _get_credentials
    HostDBConnector     CiliumLocalRedirectPolicy    dynamic-credentials Secret
    HostAdminDBConnector     (inherited)             superuser Secret
    ClusterDBConnector  in-cluster Service           OpenBao database/creds
    ClusterAdminDBConnector  (inherited)             OpenBao KV superuser entry
"""

import base64
import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from functools import cached_property
from pathlib import Path
from typing import Any

import geopandas as gpd
import hvac
import kubernetes as k8s
import sqlalchemy as sql
from sqlalchemy import event

CREDENTIAL_KEYS = ("username", "password")


def _first_env(*names: str) -> str | None:
    """Returns the value of the first of the given environment variables that is set."""
    return next((os.environ[name] for name in names if name in os.environ), None)


def _username_password(data: Mapping[str, Any], source: str) -> tuple[Any, Any]:
    """Returns data's username and password, raising if either is missing."""
    missing_keys = [key for key in CREDENTIAL_KEYS if key not in data]
    if missing_keys:
        raise RuntimeError(f"{source} missing key(s): {', '.join(missing_keys)}")
    return (data["username"], data["password"])


class DBConnector(ABC):
    """Connects to a PostgreSQL database and queries it.

    The engine's URL holds no address or login. Both are filled in each time
    SQLAlchemy opens a new connection, so a rotated password reaches the next
    connection without rebuilding the engine."""

    def __init__(
        self,
        database: str = "data_science",
        target_resolver: Callable[[], tuple[str, int]] | None = None,
    ) -> None:
        self.database = database
        self.host, self.port = (target_resolver or self._get_target)()
        self.engine = self._create_engine()

    @abstractmethod
    def _get_target(self) -> tuple[str, int]:
        """Returns the (host, port) to connect to."""
        raise NotImplementedError

    @abstractmethod
    def _get_credentials(self) -> tuple[str, str]:
        """Returns a fresh (username, password) pair."""
        raise NotImplementedError

    def _create_engine(self) -> sql.Engine:
        """Returns an engine that fills in the address and login per connection."""
        engine = sql.create_engine("postgresql+psycopg://")

        @event.listens_for(engine, "do_connect")
        def _inject_credentials(dialect, conn_rec, cargs, cparams) -> None:
            username, password = self._get_credentials()
            cparams.update(
                user=username,
                password=password,
                host=self.host,
                port=self.port,
                dbname=self.database,
            )

        return engine

    def db_query(
        self,
        query_file: str | Path | None = None,
        *,
        query: str | None = None,
        geom_col: str,
    ) -> gpd.GeoDataFrame:
        """Runs a SQL query against the PostGIS database, returning a GeoDataFrame.

        Give exactly one of query_file (a path to a .sql file) or query (a
        literal SQL string). geom_col names the one geometry column to decode.
        """
        if query is not None and query_file is None:
            sql_text = query
        elif query_file is not None and query is None:
            sql_text = Path(query_file).read_text()
        else:
            raise ValueError("give exactly one of query_file or query")
        return gpd.read_postgis(sql=sql_text, con=self.engine, geom_col=geom_col)


class HostDBConnector(DBConnector):
    """Connects to the database from outside the cluster, through the current
    kubeconfig context, using the operator-synced dynamic-credentials Secret."""

    POLICY_KIND: str = "CiliumLocalRedirectPolicy"
    POLICY_LABEL: str = "app.kubernetes.io/name=postgis-cluster"
    SECRET_NAME: str = "postgis-app-dynamic-credentials"
    SECRET_NAMESPACE: str = "databases"

    @cached_property
    def _api_client(self) -> k8s.client.ApiClient:
        """Returns this connector's own client for the current kubeconfig context,
        leaving the process-wide default configuration untouched."""
        return k8s.config.new_client_from_config()

    def _get_target(self) -> tuple[str, int]:
        """Returns the (host, port) from the cluster's CiliumLocalRedirectPolicy."""
        group, plural, version = self._policy_resource()
        raw_result = k8s.client.CustomObjectsApi(
            self._api_client
        ).list_cluster_custom_object(
            group=group,
            plural=plural,
            version=version,
            label_selector=self.POLICY_LABEL,
        )
        if not isinstance(raw_result, dict):
            raise TypeError(
                "expected a dict from list_cluster_custom_object, "
                f"got {type(raw_result).__name__}"
            )
        policies = raw_result["items"]
        if len(policies) != 1:
            raise RuntimeError(
                f"expected exactly one {self.POLICY_KIND} matching label "
                f"{self.POLICY_LABEL}, found {len(policies)}"
            )
        address_matcher = policies[0]["spec"]["redirectFrontend"]["addressMatcher"]
        return (address_matcher["ip"], int(address_matcher["toPorts"][0]["port"]))

    def _policy_resource(self) -> tuple[str, str, str]:
        """Returns the policy CRD's (group, plural, storage version)."""
        crd_list = k8s.client.ApiextensionsV1Api(
            self._api_client
        ).list_custom_resource_definition()
        policy_crd = next(
            (crd for crd in crd_list.items if crd.spec.names.kind == self.POLICY_KIND),
            None,
        )
        if policy_crd is None:
            raise RuntimeError(f"no {self.POLICY_KIND} CRD; is Cilium installed?")
        served = [version for version in policy_crd.spec.versions if version.served]
        if not served:
            raise RuntimeError(f"{self.POLICY_KIND} CRD has no served version")
        storage = [version for version in served if version.storage]
        if not storage:
            raise RuntimeError(
                f"{self.POLICY_KIND} CRD has no storage version among its "
                "served versions"
            )
        if len(storage) > 1:
            raise RuntimeError(f"{self.POLICY_KIND} CRD has multiple storage versions")
        return (policy_crd.spec.group, policy_crd.spec.names.plural, storage[0].name)

    def _get_credentials(self) -> tuple[str, str]:
        """Returns a fresh (username, password) pair decoded from the Secret."""
        secret = k8s.client.CoreV1Api(self._api_client).read_namespaced_secret(
            self.SECRET_NAME, self.SECRET_NAMESPACE
        )
        if secret.data is None:
            raise RuntimeError(f"{self.SECRET_NAME} Secret has no data")
        encoded = _username_password(secret.data, f"{self.SECRET_NAME} Secret")
        username, password = (base64.b64decode(value).decode() for value in encoded)
        return (username, password)


class HostAdminDBConnector(HostDBConnector):
    """Connects to the database from outside the cluster using the Postgres
    superuser credential, for schema/DDL changes rather than routine queries.

    Unlike HostDBConnector's dynamic lease, this credential is static
    (doesn't expire or rotate) and unscoped to a single database — it's the
    same credential CloudNativePG itself uses for cluster bootstrap and
    reconciliation. Use deliberately, not as a default."""

    SECRET_NAME: str = "postgis-app-credentials"


class ClusterDBConnector(DBConnector):
    """Connects to the database from inside a pod, using short-lived
    credentials generated by OpenBao or Vault on every new connection.

    Logs in with Kubernetes auth as AUTH_ROLE, sending the projected service
    account token at TOKEN_PATH, then reads database/creds/DATABASE_ROLE.
    The server address comes from BAO_ADDR, then VAULT_ADDR, and its CA file
    from BAO_CACERT, then VAULT_CACERT. Leases are not revoked; each ends at
    its TTL."""

    HOST: str = "postgis-cluster-rw.databases.svc.cluster.local"
    PORT: int = 5432
    DATABASE_ROLE: str = "postgis-app-role"
    AUTH_ROLE: str | None = None
    TOKEN_PATH: str = "/var/run/secrets/openbao/token"

    def _get_target(self) -> tuple[str, int]:
        """Returns the in-cluster read-write Service address."""
        return (self.HOST, self.PORT)

    def _get_credentials(self) -> tuple[str, str]:
        """Returns a fresh (username, password) pair from the secrets backend."""
        data = self._read_credentials(self._logged_in_client())
        if not isinstance(data, dict):
            raise TypeError(f"expected a data mapping from {self._credentials_path()}")
        return _username_password(data, f"{self._credentials_path()} response")

    def _logged_in_client(self) -> hvac.Client:
        """Returns a client logged in to the backend as AUTH_ROLE."""
        if self.AUTH_ROLE is None:
            raise RuntimeError(
                "set AUTH_ROLE to the Kubernetes auth role this pod logs in as"
            )
        try:
            token = Path(self.TOKEN_PATH).read_text().strip()
        except FileNotFoundError as error:
            raise RuntimeError(
                f"no service account token at {self.TOKEN_PATH}; "
                "mount a projected token or set TOKEN_PATH"
            ) from error
        url = _first_env("BAO_ADDR", "VAULT_ADDR")
        if url is None:
            raise RuntimeError(
                "set BAO_ADDR or VAULT_ADDR to the secrets backend's address"
            )
        ca_cert = _first_env("BAO_CACERT", "VAULT_CACERT")
        client = hvac.Client(url=url, verify=ca_cert or True)
        client.auth.kubernetes.login(role=self.AUTH_ROLE, jwt=token)
        return client

    def _credentials_path(self) -> str:
        """Returns the backend path the credentials come from, for error messages."""
        return f"database/creds/{self.DATABASE_ROLE}"

    def _read_credentials(self, client: hvac.Client) -> object:
        """Returns the data of a newly generated database login."""
        response = client.secrets.database.generate_credentials(name=self.DATABASE_ROLE)
        return response.get("data") if isinstance(response, dict) else None


class ClusterAdminDBConnector(ClusterDBConnector):
    """Connects to the database from inside a pod using the Postgres superuser
    credential, for schema/DDL changes rather than routine queries.

    Logs in to the secrets backend the same way as ClusterDBConnector, then
    reads the static KV v2 entry KV_MOUNT/KV_PATH in place of a dynamic lease.
    It's the entry External Secrets Operator syncs into the Secret
    HostAdminDBConnector reads, so the same cautions apply: the credential
    doesn't expire and isn't scoped to one database. AUTH_ROLE must have a
    policy that can read it. Use deliberately, not as a default."""

    KV_MOUNT: str = "secret"
    KV_PATH: str = "postgis"

    def _credentials_path(self) -> str:
        """Returns the KV entry the credentials come from, for error messages."""
        return f"{self.KV_MOUNT}/{self.KV_PATH}"

    def _read_credentials(self, client: hvac.Client) -> object:
        """Returns the data of the latest version of the KV entry."""
        response = client.secrets.kv.v2.read_secret_version(
            path=self.KV_PATH, mount_point=self.KV_MOUNT, raise_on_deleted_version=True
        )
        data = response.get("data") if isinstance(response, dict) else None
        return data.get("data") if isinstance(data, dict) else None
