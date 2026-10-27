"""Tests for src/pgiscluster/connector.py"""

from pathlib import Path
from unittest.mock import MagicMock

import geopandas as gpd
import pytest

from pgiscluster import HostAdminDBConnector, HostDBConnector
from tests.conftest import (
    FakeKube,
    FakeVault,
    make_crd,
    make_policy,
    make_secret,
    make_token_request,
    static_target,
)

LABEL = "app.kubernetes.io/name=postgres-cluster"


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
    kube.custom_objects_api.list_cluster_custom_object.assert_called_once_with(
        group="cilium.io",
        plural="ciliumlocalredirectpolicies",
        version="v2",
        label_selector=LABEL,
    )


def given_openbao_login(kube: FakeKube, fake_vault: FakeVault) -> None:
    kube.core_api.create_namespaced_service_account_token.return_value = (
        make_token_request("kube-jwt")
    )
    fake_vault.returns({"username": "v-app", "password": "pw"})


def test_host_connector_uses_its_own_kubeconfig_client(
    kube: FakeKube, fake_vault: FakeVault
) -> None:
    """when: a HostDBConnector resolves its target and requests its token
    then: both go through one ApiClient built from the kubeconfig, and the
    process-wide default configuration is never touched"""
    given_policies(kube, make_policy("169.254.0.5", 5432))
    given_openbao_login(kube, fake_vault)

    HostDBConnector()._get_credentials()

    kube.new_client_from_config.assert_called_once_with()
    kube.load_kube_config.assert_not_called()


def test_host_get_credentials_loads_kubeconfig_with_target_resolver(
    kube: FakeKube, fake_vault: FakeVault
) -> None:
    """given: a target_resolver, so the Cilium lookup never runs
    when: _get_credentials is called
    then: the kubeconfig is still loaded for the token request"""
    given_openbao_login(kube, fake_vault)

    HostDBConnector(target_resolver=static_target)._get_credentials()

    kube.new_client_from_config.assert_called_once_with()


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
    """given: zero or several policies match the postgres-cluster label
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


def test_host_get_credentials_logs_in_to_openbao_with_a_service_account_token(
    kube: FakeKube, fake_vault: FakeVault
) -> None:
    """given: the API server issues a token for databases-openbao-auth, and OpenBao
    returns a login for postgres-app-role
    then: logs in as databases-role with that token and returns that login"""
    given_openbao_login(kube, fake_vault)

    credentials = HostDBConnector(target_resolver=static_target)._get_credentials()

    assert credentials == ("v-app", "pw")
    name, namespace, request = (
        kube.core_api.create_namespaced_service_account_token.call_args.args
    )
    assert (name, namespace) == ("databases-openbao-auth", "databases")
    assert request.spec.audiences == ["openbao"]
    assert request.spec.expiration_seconds == 600
    fake_vault.client.auth.kubernetes.login.assert_called_once_with(
        role="databases-role", jwt="kube-jwt"
    )
    fake_vault.client.secrets.database.generate_credentials.assert_called_once_with(
        name="postgres-app-role"
    )


def test_host_get_credentials_fetches_fresh_each_call(
    kube: FakeKube, fake_vault: FakeVault
) -> None:
    """given: OpenBao returns a different login on each read
    then: each call requests a token, logs in and reads again"""
    kube.core_api.create_namespaced_service_account_token.return_value = (
        make_token_request("kube-jwt")
    )
    fake_vault.returns(
        {"username": "v-1", "password": "pw-1"},
        {"username": "v-2", "password": "pw-2"},
    )
    connector = HostDBConnector(target_resolver=static_target)

    assert connector._get_credentials() == ("v-1", "pw-1")
    assert connector._get_credentials() == ("v-2", "pw-2")
    assert kube.core_api.create_namespaced_service_account_token.call_count == 2


def test_host_get_credentials_defaults_to_the_local_redirect(
    kube: FakeKube, fake_vault: FakeVault, monkeypatch: pytest.MonkeyPatch
) -> None:
    """given: neither BAO_ADDR nor VAULT_ADDR is set
    then: the client connects to OpenBao's local redirect at 127.0.0.1:8210"""
    monkeypatch.delenv("BAO_ADDR")
    given_openbao_login(kube, fake_vault)

    HostDBConnector(target_resolver=static_target)._get_credentials()

    fake_vault.client_class.assert_called_once_with(
        url="https://127.0.0.1:8210", verify=True
    )


# --- HostAdminDBConnector._get_credentials ---


def test_admin_get_credentials_returns_the_superuser_secret(kube: FakeKube) -> None:
    """given: the superuser Secret holds base64 username and password
    then: returns the decoded (username, password) tuple"""
    kube.core_api.read_namespaced_secret.return_value = make_secret("postgres", "pw")

    credentials = HostAdminDBConnector(target_resolver=static_target)._get_credentials()

    assert credentials == ("postgres", "pw")
    kube.core_api.read_namespaced_secret.assert_called_once_with(
        "postgres-superuser-credentials", "databases"
    )


@pytest.mark.parametrize(
    ("username", "password", "missing"),
    [("postgres", None, "password"), (None, "pw", "username")],
)
def test_admin_get_credentials_raises_when_secret_missing_username_or_password(
    kube: FakeKube, username: str | None, password: str | None, missing: str
) -> None:
    """given: the Secret's data lacks username or password
    then: raises RuntimeError naming the missing key"""
    kube.core_api.read_namespaced_secret.return_value = make_secret(username, password)

    with pytest.raises(RuntimeError, match=f"missing key\\(s\\): {missing}$"):
        HostAdminDBConnector(target_resolver=static_target)._get_credentials()


def test_admin_get_credentials_raises_when_secret_has_no_data(kube: FakeKube) -> None:
    """given: the Secret has no data at all
    then: raises RuntimeError naming the Secret"""
    kube.core_api.read_namespaced_secret.return_value = make_secret(None, None)
    kube.core_api.read_namespaced_secret.return_value.data = None

    with pytest.raises(
        RuntimeError, match="postgres-superuser-credentials Secret has no data"
    ):
        HostAdminDBConnector(target_resolver=static_target)._get_credentials()


# --- DBConnector._create_engine ---


def test_create_engine_do_connect_event_populates_cparams(
    kube: FakeKube, fake_vault: FakeVault
) -> None:
    """given: a connector with known host and port, and an OpenBao login
    when: the engine's do_connect event fires
    then: user, password, host, port and dbname are filled in from those sources"""
    given_openbao_login(kube, fake_vault)
    connector = HostDBConnector(database="gis", target_resolver=static_target)
    cparams: dict = {}

    connector.engine.dialect.dispatch.do_connect(
        connector.engine.dialect, None, [], cparams
    )

    assert cparams == {
        "user": "v-app",
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


@pytest.mark.parametrize(
    "sources",
    [{}, {"query_file": "nearby.sql", "query": "SELECT 1"}],
    ids=["neither", "both"],
)
def test_db_query_raises_unless_exactly_one_source(
    kube: FakeKube, sources: dict[str, str]
) -> None:
    """when: db_query is called with neither or both of query_file and query
    then: raises ValueError"""
    connector = HostDBConnector(target_resolver=static_target)

    with pytest.raises(ValueError, match="exactly one of query_file or query"):
        connector.db_query(**sources, geom_col="geom")
