"""Fixtures for pgiscluster"""

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, create_autospec

import hvac
import kubernetes as k8s
import pytest
from kubernetes.client import (
    V1CustomResourceDefinition,
    V1CustomResourceDefinitionList,
    V1CustomResourceDefinitionNames,
    V1CustomResourceDefinitionSpec,
    V1CustomResourceDefinitionVersion,
    V1ObjectMeta,
    V1Secret,
)


def base64_encode(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def make_crd(
    versions: list[tuple[str, bool, bool]],
) -> V1CustomResourceDefinitionList:
    """Builds a CRD list holding the CiliumLocalRedirectPolicy CRD, with
    versions given as (name, served, storage)."""
    policy_crd = V1CustomResourceDefinition(
        metadata=V1ObjectMeta(name="ciliumlocalredirectpolicies.cilium.io"),
        spec=V1CustomResourceDefinitionSpec(
            group="cilium.io",
            names=V1CustomResourceDefinitionNames(
                kind="CiliumLocalRedirectPolicy",
                plural="ciliumlocalredirectpolicies",
            ),
            scope="Namespaced",
            versions=[
                V1CustomResourceDefinitionVersion(
                    name=name, served=served, storage=storage
                )
                for name, served, storage in versions
            ],
        ),
    )
    return V1CustomResourceDefinitionList(items=[policy_crd])


def make_policy(ip: str, port: int) -> dict[str, Any]:
    """Builds a policy instance shaped like apps/databases/postgis-localhost.yaml."""
    return {
        "metadata": {"name": "postgis-localhost", "namespace": "databases"},
        "spec": {
            "redirectFrontend": {
                "addressMatcher": {
                    "ip": ip,
                    "toPorts": [{"port": str(port), "protocol": "TCP"}],
                }
            }
        },
    }


def make_secret(username: str | None, password: str | None) -> V1Secret:
    """Builds a Secret with base64-encoded data, leaving out any key given as None."""
    data: dict[str, bytes | str] = {
        key: base64_encode(value)
        for key, value in (("username", username), ("password", password))
        if value is not None
    }
    return V1Secret(data=data)


def static_target() -> tuple[str, int]:
    return ("db", 5432)


@dataclass
class FakeKube:
    load_kube_config: MagicMock
    new_client_from_config: MagicMock
    extensions_api: MagicMock
    custom_objects_api: MagicMock
    core_api: MagicMock


@pytest.fixture
def kube(monkeypatch: pytest.MonkeyPatch) -> FakeKube:
    """Replaces the Kubernetes config loaders and API classes with autospecced mocks."""
    load_kube_config = MagicMock()
    monkeypatch.setattr(k8s.config, "load_kube_config", load_kube_config)
    new_client_from_config = MagicMock()
    monkeypatch.setattr(k8s.config, "new_client_from_config", new_client_from_config)
    apis = {}
    for name in ("ApiextensionsV1Api", "CustomObjectsApi", "CoreV1Api"):
        api_class = create_autospec(getattr(k8s.client, name))
        monkeypatch.setattr(k8s.client, name, api_class)
        apis[name] = api_class.return_value
    return FakeKube(
        load_kube_config=load_kube_config,
        new_client_from_config=new_client_from_config,
        extensions_api=apis["ApiextensionsV1Api"],
        custom_objects_api=apis["CustomObjectsApi"],
        core_api=apis["CoreV1Api"],
    )


@dataclass
class FakeVault:
    client_class: MagicMock
    client: MagicMock
    token_path: Path

    def returns(self, *credentials: dict[str, str]) -> None:
        """Queues one database credentials response per given data dict."""
        self.client.secrets.database.generate_credentials.side_effect = [
            {"lease_id": f"lease-{index}", "data": data}
            for index, data in enumerate(credentials)
        ]

    def returns_kv(self, *credentials: dict[str, str]) -> None:
        """Queues one KV v2 read response per given data dict."""
        self.client.secrets.kv.v2.read_secret_version.side_effect = [
            {"data": {"data": data, "metadata": {"version": index + 1}}}
            for index, data in enumerate(credentials)
        ]


@pytest.fixture
def fake_vault(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeVault:
    """Replaces hvac.Client with a mock, points BAO_ADDR at a fake server, and
    writes a projected token file under tmp_path."""
    for variable in ("BAO_ADDR", "VAULT_ADDR", "BAO_CACERT", "VAULT_CACERT"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("BAO_ADDR", "https://openbao.example:8200")
    client = MagicMock(spec_set=hvac.Client)
    client_class = MagicMock(return_value=client)
    monkeypatch.setattr(hvac, "Client", client_class)
    token_path = tmp_path / "token"
    token_path.write_text("projected-jwt")
    return FakeVault(client_class=client_class, client=client, token_path=token_path)
