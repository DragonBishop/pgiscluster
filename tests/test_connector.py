# Test plan for src/pgiscluster/connector.py

# --- DBConnector._get_target ---

# test_get_target_returns_host_and_port_on_happy_path
#   given: mocked ApiextensionsV1Api returns the CiliumLocalRedirectPolicy CRD with
#     one served version marked as storage
#   and: mocked CustomObjectsApi.list_cluster_custom_object returns exactly one
#     matching policy instance, shaped like apps/databases/postgis-localhost.yaml
#   when: _get_target is called
#   then: returns (ip, port) extracted from that instance's redirectFrontend.addressMatcher

# test_get_target_raises_when_crd_has_no_served_version
#   given: no version in the CRD's spec.versions is marked served
#   when: _get_target is called
#   then: raises RuntimeError naming the CRD and "no served version"

# test_get_target_raises_when_no_storage_version_among_served
#   given: served versions exist but none is marked storage
#   when: _get_target is called
#   then: raises RuntimeError naming the CRD and "no storage version"

# test_get_target_raises_when_multiple_storage_versions
#   given: more than one served version is marked storage
#   when: _get_target is called
#   then: raises RuntimeError naming the CRD and "multiple storage versions"

# test_get_target_raises_when_zero_policies_match_label
#   given: list_cluster_custom_object returns zero items for the
#     app.kubernetes.io/name=postgis-cluster label
#   when: _get_target is called
#   then: raises RuntimeError naming the label and the count found (0)

# test_get_target_raises_when_multiple_policies_match_label
#   given: list_cluster_custom_object returns more than one item for that label
#   when: _get_target is called
#   then: raises RuntimeError naming the label and the count found (>1)

# --- HostDBConnector._get_credentials ---

# test_get_credentials_returns_username_and_password_from_synced_secret
#   given: mocked CoreV1Api.read_namespaced_secret("postgis-app-dynamic-credentials",
#     "databases") returns a Secret with base64-encoded "username" and "password" data
#   when: _get_credentials is called
#   then: returns the decoded (username, password) tuple

# test_get_credentials_fetches_fresh_each_call
#   given: the mocked Secret read returns different values on two successive calls
#     (simulating Vault's lease rotation / VSO's refreshAfter)
#   when: _get_credentials is called twice
#   then: read_namespaced_secret is called each time, not cached, and each call
#     returns that call's current values

# test_get_credentials_raises_when_secret_missing_username_or_password
#   given: the Secret's data is missing "username" or "password"
#   when: _get_credentials is called
#   then: raises RuntimeError naming the missing key

# --- ClusterDBConnector._get_credentials ---

# test_get_credentials_returns_username_and_password_from_vault
#   given: mocked hvac client read of "database/creds/postgis-app-role" returns
#     data containing "username" and "password"
#   when: _get_credentials is called
#   then: returns that (username, password) tuple

# test_get_credentials_fetches_fresh_each_call
#   given: the mocked hvac read returns different lease credentials on two
#     successive calls
#   when: _get_credentials is called twice
#   then: the Vault read happens each time, not cached, and each call returns
#     that call's current values

# test_get_credentials_raises_when_vault_response_missing_credentials
#   given: the hvac response data is missing "username" or "password"
#   when: _get_credentials is called
#   then: raises RuntimeError naming the missing key

# --- DBConnector._create_engine ---

# test_create_engine_do_connect_event_populates_cparams
#   given: a DBConnector instance with known host/port and a fake _get_credentials
#   when: the engine's "do_connect" event fires
#   then: cparams["user"], ["password"], ["host"], ["port"], ["dbname"] match those sources

# --- DBConnector.db_query ---

# test_db_query_calls_read_postgis_with_given_args
#   given: a DBConnector with a mocked engine
#   when: db_query(query, geom_col) is called
#   then: geopandas.read_postgis is called with that query, the engine, and that geom_col
