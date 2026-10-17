"""Tests for src/pgiscluster/connector.py"""

from pathlib import Path
from unittest.mock import MagicMock

import geopandas as gpd
import pytest

from pgiscluster import HostDBConnector
from tests.conftest import (
    FakeKube,
    make_crd,
    make_policy,
    make_secret,
    static_target,
)

LABEL = "app.kubernetes.io/name=postgis-cluster"


# --- DBConnector._get_target ---


def given_policies(kube: FakeKube, *policies: dict) -> None:
    kube.extensions_api.list_custom_resource_definition.return_value = make_crd(
        [("v2", True, True)]
    )
    kube.custom_objects_api.list_cluster_custom_object.return_value = {
        "items": list(policies)
    }


def test_get_target_returns_host_and_port_on_happy_path(kube: FakeKube) -> None:
    """given: the CiliumLocalRedirectPolicy CRD with one served storage version,
    and exactly one matching policy instance
    then: returns (ip, port) from that instance's redirectFrontend.addressMatcher"""
    given_policies(kube, make_policy("169.254.0.5", 5432))

    connector = HostDBConnector()

    assert (connector.host, connector.port) == ("169.254.0.5", 5432)
    kube.load_kube_config.assert_called_once_with()
    kube.custom_objects_api.list_cluster_custom_object.assert_called_once_with(
        group="cilium.io",
        plural="ciliumlocalredirectpolicies",
        version="v2",
        label_selector=LABEL,
    )


@pytest.mark.parametrize(
    ("versions", "message"),
    [
        pytest.param([("v2", False, True)], "no served version", id="no-served"),
        pytest.param(
            [("v2", True, False), ("v2alpha1", True, False)],
            "no storage version",
            id="no-storage-among-served",
        ),
        pytest.param(
            [("v2", True, True), ("v2alpha1", True, True)],
            "multiple storage versions",
            id="multiple-storage",
        ),
    ],
)
def test_get_target_raises_on_unusable_crd_versions(
    kube: FakeKube, versions: list[tuple[str, bool, bool]], message: str
) -> None:
    """given: the CRD's versions have no served version, no storage version among
    the served ones, or more than one storage version
    then: raises RuntimeError naming the CRD and the problem"""
    kube.extensions_api.list_custom_resource_definition.return_value = make_crd(
        versions
    )

    with pytest.raises(
        RuntimeError, match=f"CiliumLocalRedirectPolicy CRD has {message}"
    ):
        HostDBConnector()


@pytest.mark.parametrize("count", [0, 2], ids=["zero", "multiple"])
def test_get_target_raises_unless_exactly_one_policy_matches_label(
    kube: FakeKube, count: int
) -> None:
    """given: zero or several policies match the postgis-cluster label
    then: raises RuntimeError naming the label and the count found"""
    given_policies(kube, *[make_policy("169.254.0.5", 5432)] * count)

    with pytest.raises(RuntimeError, match=rf"{LABEL}, found {count}$"):
        HostDBConnector()


def test_get_target_raises_when_custom_object_response_is_not_a_dict(
    kube: FakeKube,
) -> None:
    """given: list_cluster_custom_object returns something other than a dict
    then: raises TypeError naming the type"""
    given_policies(kube)
    kube.custom_objects_api.list_cluster_custom_object.return_value = []

    with pytest.raises(TypeError, match="got list"):
        HostDBConnector()


# --- HostDBConnector._get_credentials ---


def test_get_credentials_returns_username_and_password_from_synced_secret(
    kube: FakeKube,
) -> None:
    """given: the dynamic-credentials Secret holds base64 username and password
    then: returns the decoded (username, password) tuple"""
    kube.core_api.read_namespaced_secret.return_value = make_secret("app", "pw")

    credentials = HostDBConnector(target_resolver=static_target)._get_credentials()

    assert credentials == ("app", "pw")
    kube.core_api.read_namespaced_secret.assert_called_once_with(
        "postgis-app-dynamic-credentials", "databases"
    )


def test_host_get_credentials_fetches_fresh_each_call(kube: FakeKube) -> None:
    """given: the Secret changes between two reads, as when the operator rotates it
    then: each call reads the Secret again and returns that read's values"""
    kube.core_api.read_namespaced_secret.side_effect = [
        make_secret("app-1", "pw-1"),
        make_secret("app-2", "pw-2"),
    ]
    connector = HostDBConnector(target_resolver=static_target)

    assert connector._get_credentials() == ("app-1", "pw-1")
    assert connector._get_credentials() == ("app-2", "pw-2")
    assert kube.core_api.read_namespaced_secret.call_count == 2


@pytest.mark.parametrize(
    ("username", "password", "missing"),
    [("app", None, "password"), (None, "pw", "username")],
)
def test_get_credentials_raises_when_secret_missing_username_or_password(
    kube: FakeKube, username: str | None, password: str | None, missing: str
) -> None:
    """given: the Secret's data lacks username or password
    then: raises RuntimeError naming the missing key"""
    kube.core_api.read_namespaced_secret.return_value = make_secret(username, password)

    with pytest.raises(RuntimeError, match=f"missing key\\(s\\): {missing}$"):
        HostDBConnector(target_resolver=static_target)._get_credentials()


def test_get_credentials_raises_when_secret_has_no_data(kube: FakeKube) -> None:
    """given: the Secret has no data at all
    then: raises RuntimeError naming the Secret"""
    kube.core_api.read_namespaced_secret.return_value = make_secret(None, None)
    kube.core_api.read_namespaced_secret.return_value.data = None

    with pytest.raises(
        RuntimeError, match="postgis-app-dynamic-credentials Secret has no data"
    ):
        HostDBConnector(target_resolver=static_target)._get_credentials()


# --- DBConnector._create_engine ---


def test_create_engine_do_connect_event_populates_cparams(kube: FakeKube) -> None:
    """given: a connector with known host and port, and a Secret with credentials
    when: the engine's do_connect event fires
    then: user, password, host, port and dbname are filled in from those sources"""
    kube.core_api.read_namespaced_secret.return_value = make_secret("app", "pw")
    connector = HostDBConnector(database="gis", target_resolver=static_target)
    cparams: dict = {}

    connector.engine.dialect.dispatch.do_connect(
        connector.engine.dialect, None, [], cparams
    )

    assert cparams == {
        "user": "app",
        "password": "pw",
        "host": "db",
        "port": 5432,
        "dbname": "gis",
    }


# --- DBConnector.db_query ---


@pytest.fixture
def read_postgis(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock(return_value=gpd.GeoDataFrame())
    monkeypatch.setattr(gpd, "read_postgis", fake)
    return fake


def test_db_query_calls_read_postgis_with_given_args(
    kube: FakeKube, read_postgis: MagicMock
) -> None:
    """when: db_query(query=..., geom_col=...) is called
    then: read_postgis gets that query, the engine and that geom_col"""
    connector = HostDBConnector(target_resolver=static_target)

    result = connector.db_query(query="SELECT 1", geom_col="geom")

    assert result is read_postgis.return_value
    read_postgis.assert_called_once_with(
        sql="SELECT 1", con=connector.engine, geom_col="geom"
    )


def test_db_query_reads_sql_from_query_file(
    kube: FakeKube, read_postgis: MagicMock, tmp_path: Path
) -> None:
    """given: a .sql file
    when: db_query(path, geom_col=...) is called
    then: read_postgis gets the file's contents"""
    query_file = tmp_path / "nearby.sql"
    query_file.write_text("SELECT * FROM places")

    HostDBConnector(target_resolver=static_target).db_query(query_file, geom_col="geom")

    assert read_postgis.call_args.kwargs["sql"] == "SELECT * FROM places"


def test_db_query_raises_without_query_or_file(kube: FakeKube) -> None:
    """when: db_query is called with neither query_file nor query
    then: raises ValueError"""
    connector = HostDBConnector(target_resolver=static_target)

    with pytest.raises(ValueError, match="either query_file or query"):
        connector.db_query(geom_col="geom")
