"""Tests for ClusterDBConnector in src/pgiscluster/connector.py"""

import pytest

from pgiscluster import ClusterAdminDBConnector, ClusterDBConnector
from tests.conftest import FakeKube, FakeVault


@pytest.fixture
def connector(fake_vault: FakeVault) -> ClusterDBConnector:
    """A ClusterDBConnector with an auth role set and the fake projected token."""
    connector = ClusterDBConnector()
    connector.AUTH_ROLE = "etl-role"
    connector.TOKEN_PATH = str(fake_vault.token_path)
    return connector


# --- ClusterDBConnector._get_target ---


def test_cluster_get_target_returns_in_cluster_service(kube: FakeKube) -> None:
    """when: a ClusterDBConnector is built without a target_resolver
    then: it targets the in-cluster read-write Service, without loading a kubeconfig"""
    connector = ClusterDBConnector()

    assert (connector.host, connector.port) == (
        "postgis-cluster-rw.databases.svc.cluster.local",
        5432,
    )
    kube.load_kube_config.assert_not_called()
    kube.new_client_from_config.assert_not_called()


# --- ClusterDBConnector._get_credentials ---


def test_get_credentials_returns_username_and_password_from_secrets_backend(
    fake_vault: FakeVault, connector: ClusterDBConnector
) -> None:
    """given: the backend's database/creds/postgis-app-role returns a username and
    password
    then: returns that (username, password) tuple"""
    fake_vault.returns({"username": "v-etl-abc", "password": "pw"})

    assert connector._get_credentials() == ("v-etl-abc", "pw")
    fake_vault.client.secrets.database.generate_credentials.assert_called_once_with(
        name="postgis-app-role"
    )


def test_get_credentials_fetches_fresh_each_call(
    fake_vault: FakeVault, connector: ClusterDBConnector
) -> None:
    """given: the backend returns different lease credentials on two calls
    then: each call logs in and reads the backend again, returning that call's values"""
    fake_vault.returns(
        {"username": "v-1", "password": "pw-1"},
        {"username": "v-2", "password": "pw-2"},
    )

    assert connector._get_credentials() == ("v-1", "pw-1")
    assert connector._get_credentials() == ("v-2", "pw-2")
    assert fake_vault.client.auth.kubernetes.login.call_count == 2


@pytest.mark.parametrize(
    ("data", "missing"),
    [
        ({"username": "v-1"}, "password"),
        ({"password": "pw"}, "username"),
        ({}, "username, password"),
    ],
)
def test_get_credentials_raises_when_backend_response_missing_credentials(
    fake_vault: FakeVault,
    connector: ClusterDBConnector,
    data: dict[str, str],
    missing: str,
) -> None:
    """given: the backend response data lacks username or password
    then: raises RuntimeError naming the missing key"""
    fake_vault.returns(data)

    with pytest.raises(RuntimeError, match=f"missing key\\(s\\): {missing}$"):
        connector._get_credentials()


def test_get_credentials_raises_when_backend_response_has_no_data_dict(
    fake_vault: FakeVault, connector: ClusterDBConnector
) -> None:
    """given: the backend response has no data mapping
    then: raises TypeError"""
    fake_vault.client.secrets.database.generate_credentials.return_value = {}

    with pytest.raises(TypeError, match="database/creds/postgis-app-role"):
        connector._get_credentials()


def test_get_credentials_logs_in_with_projected_token(
    fake_vault: FakeVault, connector: ClusterDBConnector
) -> None:
    """given: a projected token file at TOKEN_PATH
    then: logs in with Kubernetes auth as AUTH_ROLE, sending that file's contents"""
    fake_vault.returns({"username": "v-1", "password": "pw"})

    connector._get_credentials()

    fake_vault.client.auth.kubernetes.login.assert_called_once_with(
        role="etl-role", jwt="projected-jwt"
    )


@pytest.mark.parametrize(
    ("environment", "url", "verify"),
    [
        pytest.param(
            {"BAO_ADDR": "https://bao:8200", "VAULT_ADDR": "https://vault:8200"},
            "https://bao:8200",
            True,
            id="bao-addr-wins-no-ca",
        ),
        pytest.param(
            {"VAULT_ADDR": "https://vault:8200", "VAULT_CACERT": "/vault/ca.crt"},
            "https://vault:8200",
            "/vault/ca.crt",
            id="vault-fallback",
        ),
        pytest.param(
            {
                "BAO_ADDR": "https://bao:8200",
                "BAO_CACERT": "/bao/ca.crt",
                "VAULT_CACERT": "/vault/ca.crt",
            },
            "https://bao:8200",
            "/bao/ca.crt",
            id="bao-cacert-wins",
        ),
    ],
)
def test_vault_address_prefers_bao_over_vault_env(
    monkeypatch: pytest.MonkeyPatch,
    fake_vault: FakeVault,
    connector: ClusterDBConnector,
    environment: dict[str, str],
    url: str,
    verify: str | bool,
) -> None:
    """given: BAO_* and/or VAULT_* address and CA variables
    then: the client uses BAO_* first, then VAULT_*, and verifies with the system CAs
    when no CA file is named"""
    monkeypatch.delenv("BAO_ADDR")
    for variable, value in environment.items():
        monkeypatch.setenv(variable, value)
    fake_vault.returns({"username": "v-1", "password": "pw"})

    connector._get_credentials()

    fake_vault.client_class.assert_called_once_with(url=url, verify=verify)


def test_get_credentials_raises_when_no_address_set(
    monkeypatch: pytest.MonkeyPatch,
    fake_vault: FakeVault,
    connector: ClusterDBConnector,
) -> None:
    """given: neither BAO_ADDR nor VAULT_ADDR is set
    then: raises RuntimeError naming both, rather than falling back to localhost"""
    monkeypatch.delenv("BAO_ADDR")

    with pytest.raises(RuntimeError, match="BAO_ADDR or VAULT_ADDR"):
        connector._get_credentials()
    fake_vault.client_class.assert_not_called()


def test_get_credentials_raises_when_auth_role_unset(fake_vault: FakeVault) -> None:
    """given: AUTH_ROLE is left at its default
    then: raises RuntimeError naming AUTH_ROLE, before contacting the backend"""
    connector = ClusterDBConnector()

    with pytest.raises(RuntimeError, match="AUTH_ROLE"):
        connector._get_credentials()
    fake_vault.client_class.assert_not_called()


def test_get_credentials_raises_when_token_file_missing(
    fake_vault: FakeVault, connector: ClusterDBConnector
) -> None:
    """given: no file at TOKEN_PATH, as when the projected volume is not mounted
    then: raises RuntimeError naming the path"""
    fake_vault.token_path.unlink()

    with pytest.raises(RuntimeError, match=str(fake_vault.token_path)):
        connector._get_credentials()


# --- ClusterAdminDBConnector._get_credentials ---


@pytest.fixture
def admin_connector(fake_vault: FakeVault) -> ClusterAdminDBConnector:
    """A ClusterAdminDBConnector with an auth role set and the fake projected token."""
    connector = ClusterAdminDBConnector()
    connector.AUTH_ROLE = "postgis-role"
    connector.TOKEN_PATH = str(fake_vault.token_path)
    return connector


def test_admin_get_credentials_returns_superuser_from_kv(
    fake_vault: FakeVault, admin_connector: ClusterAdminDBConnector
) -> None:
    """given: the KV v2 entry secret/postgis holds the superuser username and password
    then: logs in as AUTH_ROLE, returns that pair, and generates no dynamic login"""
    fake_vault.returns_kv({"username": "postgres", "password": "su-pw"})

    assert admin_connector._get_credentials() == ("postgres", "su-pw")
    fake_vault.client.auth.kubernetes.login.assert_called_once_with(
        role="postgis-role", jwt="projected-jwt"
    )
    fake_vault.client.secrets.kv.v2.read_secret_version.assert_called_once_with(
        path="postgis", mount_point="secret", raise_on_deleted_version=True
    )
    fake_vault.client.secrets.database.generate_credentials.assert_not_called()


def test_admin_get_credentials_fetches_fresh_each_call(
    fake_vault: FakeVault, admin_connector: ClusterAdminDBConnector
) -> None:
    """given: the KV entry changes between two reads, as when the password is rotated
    then: each call reads the entry again and returns that read's values"""
    fake_vault.returns_kv(
        {"username": "postgres", "password": "su-1"},
        {"username": "postgres", "password": "su-2"},
    )

    assert admin_connector._get_credentials() == ("postgres", "su-1")
    assert admin_connector._get_credentials() == ("postgres", "su-2")


def test_admin_get_credentials_raises_when_kv_entry_missing_credentials(
    fake_vault: FakeVault, admin_connector: ClusterAdminDBConnector
) -> None:
    """given: the KV entry lacks a password
    then: raises RuntimeError naming the entry and the missing key"""
    fake_vault.returns_kv({"username": "postgres"})

    with pytest.raises(
        RuntimeError, match="secret/postgis response missing key\\(s\\): password$"
    ):
        admin_connector._get_credentials()


@pytest.mark.parametrize(
    "response",
    [{}, {"data": {}}, {"data": {"data": None}}],
    ids=["no-data", "no-inner-data", "null-inner-data"],
)
def test_admin_get_credentials_raises_when_kv_response_has_no_data_dict(
    fake_vault: FakeVault, admin_connector: ClusterAdminDBConnector, response: dict
) -> None:
    """given: the KV response has no data.data mapping
    then: raises TypeError naming the entry"""
    fake_vault.client.secrets.kv.v2.read_secret_version.return_value = response

    with pytest.raises(TypeError, match="secret/postgis"):
        admin_connector._get_credentials()
