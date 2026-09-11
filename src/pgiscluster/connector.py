from abc import ABC, abstractmethod
from typing import cast

import geopandas as gpd
import kubernetes as k8s
import sqlalchemy as sql
from sqlalchemy import event


class DBConnector(ABC):
    """Assembles a PostgreSQL connection address, then queries the database"""

    def __init__(self, database="data_science") -> None:
        self.drivername = "postgresql+psycopg"
        self.database = database
        self.host, self.port = self._get_target()
        self.engine = self._create_engine()

    @abstractmethod
    def _get_target(self) -> tuple[str, int]:
        """Returns the (host, port) to connect to, resolved live from the cluster's CiliumLocalRedirectPolicy."""
        k8s.config.load_kube_config()
        crd_list = cast(
            k8s.client.V1CustomResourceDefinitionList,
            k8s.client.ApiextensionsV1Api().list_custom_resource_definition(),
        )
        assert crd_list.items is not None

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
            raise RuntimeError(
                f"{local_policy.metadata.name} CRD has no served version"
            )
        storage_version_options = (
            version for version in served_versions if version.storage
        )
        storage_version = next(storage_version_options, None)
        if storage_version is None:
            raise RuntimeError(
                f"{local_policy.metadata.name} CRD has no storage version among its served versions"
            )
        if next(storage_version_options, None) is not None:
            raise RuntimeError(
                f"{local_policy.metadata.name} CRD has multiple storage versions"
            )
        result = cast(
            dict,
            k8s.client.CustomObjectsApi().list_cluster_custom_object(
                group=group,
                plural=plural,
                version=storage_version.name,
                label_selector="app.kubernetes.io/name=postgis-cluster",
            ),
        )
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

    def database_query(self, query: str, geom_col: str) -> gpd.GeoDataFrame:
        """Runs user-defined SQL query against PostGIS Database"""
        geodataframe = gpd.read_postgis(
            sql=query,
            con=self.engine,
            # NOTE: GeoDataFrame can only analyze one geometry column at a time
            geom_col=geom_col,
        )
        return geodataframe
