import base64
import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

import geopandas as gpd
import hvac
import kubernetes as k8s
import sqlalchemy as sql
from sqlalchemy import event


class DBConnector(ABC):
    """Assembles a PostgreSQL connection address, then queries the database"""

    def __init__(
        self,
        database: str = "data_science",
        target_resolver: Callable[[], tuple[str, int]] | None = None,
    ) -> None:
        self.drivername = "postgresql+psycopg"
        self.database = database
        self.host, self.port = (target_resolver or self._get_target)()
        self.engine = self._create_engine()

    def _get_target(self) -> tuple[str, int]:
        """Returns the (host, port) to connect to, resolved live from the cluster's CiliumLocalRedirectPolicy."""
        k8s.config.load_kube_config()
        crd_list = k8s.client.ApiextensionsV1Api().list_custom_resource_definition()

        local_policy = next(
            crd
            for crd in crd_list.items
            if crd.spec.names.kind == "CiliumLocalRedirectPolicy"
        )
        group = local_policy.spec.group
        plural = local_policy.spec.names.plural
        served_versions = [
            version for version in local_policy.spec.versions if version.served
        ]
        if not served_versions:
            raise RuntimeError("CiliumLocalRedirectPolicy CRD has no served version")
        storage_version_options = (
            version for version in served_versions if version.storage
        )
        storage_version = next(storage_version_options, None)
        if storage_version is None:
            raise RuntimeError(
                "CiliumLocalRedirectPolicy CRD has no storage version among its served versions"
            )
        if next(storage_version_options, None) is not None:
            raise RuntimeError(
                "CiliumLocalRedirectPolicy CRD has multiple storage versions"
            )
        raw_result = k8s.client.CustomObjectsApi().list_cluster_custom_object(
            group=group,
            plural=plural,
            version=storage_version.name,
            label_selector="app.kubernetes.io/name=postgis-cluster",
        )
        if not isinstance(raw_result, dict):
            raise TypeError(
                f"expected a dict from list_cluster_custom_object, got {type(raw_result).__name__}"
            )
        result: dict[str, Any] = raw_result
        if len(result["items"]) != 1:
            raise RuntimeError(
                f"expected exactly one CiliumLocalRedirectPolicy matching label "
                f"app.kubernetes.io/name=postgis-cluster, found {len(result['items'])}"
            )
        address_matcher = result["items"][0]["spec"]["redirectFrontend"][
            "addressMatcher"
        ]
        host = address_matcher["ip"]
        port = int(address_matcher["toPorts"][0]["port"])
        return (host, port)

    @abstractmethod
    def _get_credentials(self) -> tuple[str, str]:
        """Returns a fresh (username, password) pair."""
        raise NotImplementedError

    def _create_engine(self) -> sql.Engine:
        """Uses DBConnector attributes to return database address."""
        engine = sql.create_engine(f"{self.drivername}://")

        @event.listens_for(engine, "do_connect")
        def _inject_credentials(*args):
            *_, cparams = args
            username, password = self._get_credentials()
            cparams["user"] = username
            cparams["password"] = password
            cparams["host"] = self.host
            cparams["port"] = self.port
            cparams["dbname"] = self.database

        return engine

    def db_query(
        self,
        query_file: str | Path | None = None,
        *,
        query: str | None = None,
        geom_col: str,
    ) -> gpd.GeoDataFrame:
        """Runs a SQL query against the PostGIS database, returning a GeoDataFrame.

        Provide query_file (a path to a .sql file) or query (a literal SQL string).
        """
        if query is None:
            if query_file is None:
                raise ValueError("either query_file or query must be given")
            query = Path(query_file).read_text()
        geodataframe = gpd.read_postgis(
            sql=query,
            con=self.engine,
            # NOTE: GeoDataFrame can only analyze one geometry column at a time
            geom_col=geom_col,
        )
        return geodataframe


class HostDBConnector(DBConnector):
    """Connects to the database from outside the cluster, using
    the operator-synced dynamic-credentials Secret."""

    SECRET_NAME = "postgis-app-dynamic-credentials"
    SECRET_NAMESPACE = "databases"

    def _get_credentials(self) -> tuple[str, str]:
        """Returns a fresh (username, password) pair decoded from the operator-synced Secret."""
        secret = k8s.client.CoreV1Api().read_namespaced_secret(
            self.SECRET_NAME, self.SECRET_NAMESPACE
        )
        if secret.data is None:
            raise RuntimeError(f"{self.SECRET_NAME} Secret has no data")
        missing_keys = [
            key for key in ("username", "password") if key not in secret.data
        ]
        if missing_keys:
            raise RuntimeError(
                f"{self.SECRET_NAME} Secret missing key(s): {', '.join(missing_keys)}"
            )
        username = base64.b64decode(secret.data["username"]).decode()
        password = base64.b64decode(secret.data["password"]).decode()
        return (username, password)


class HostAdminDBConnector(HostDBConnector):
    """Connects to the database from outside the cluster using the Postgres
    superuser credential, for schema/DDL changes rather than routine queries.

    Unlike HostDBConnector's dynamic lease, this credential is static
    (doesn't expire or rotate) and unscoped to a single database — it's the
    same credential CloudNativePG itself uses for cluster bootstrap and
    reconciliation. Use deliberately, not as a default."""

    SECRET_NAME = "postgis-app-credentials"


def _first_env(*names: str) -> str | None:
    """Returns the value of the first of the given environment variables that is set."""
    return next((os.environ[name] for name in names if name in os.environ), None)


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

    def _vault_client(self) -> hvac.Client:
        """Returns a client for the server named by BAO_ADDR or VAULT_ADDR."""
        url = _first_env("BAO_ADDR", "VAULT_ADDR")
        if url is None:
            raise RuntimeError(
                "set BAO_ADDR or VAULT_ADDR to the secrets backend's address"
            )
        ca_cert = _first_env("BAO_CACERT", "VAULT_CACERT")
        return hvac.Client(url=url, verify=ca_cert or True)

    def _get_credentials(self) -> tuple[str, str]:
        """Returns a fresh (username, password) pair generated by the secrets backend."""
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
        client = self._vault_client()
        client.auth.kubernetes.login(role=self.AUTH_ROLE, jwt=token)
        creds_path = f"database/creds/{self.DATABASE_ROLE}"
        response = client.secrets.database.generate_credentials(name=self.DATABASE_ROLE)
        data = response.get("data") if isinstance(response, dict) else None
        if not isinstance(data, dict):
            raise TypeError(f"expected a data mapping from {creds_path}")
        missing_keys = [key for key in ("username", "password") if key not in data]
        if missing_keys:
            raise RuntimeError(
                f"{creds_path} response missing key(s): {', '.join(missing_keys)}"
            )
        return (data["username"], data["password"])
