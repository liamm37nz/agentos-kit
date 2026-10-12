import copy

import pytest

from agentos_kit import manifest as mf

VALID = {
    "spec": "agentos/v1",
    "id": "gst",
    "name": "GST",
    "description": "Prepares GST returns.",
    "network": "internet",
    "jobs": [{"id": "prepare-return", "name": "Prepare", "schedule": "0 6 1 2,4,6,8,10,12 *", "catch_up": "once"}],
    "secrets": [{"name": "AKAHU_USER_TOKEN", "description": "Akahu"}],
    "shared": [{"path": "obsidian", "mount": "/vault"}],
    "egress": [{"host": "api.akahu.io", "purpose": "Read transactions"}],
}


def variant(**changes):
    data = copy.deepcopy(VALID)
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return data


def test_valid_manifest_gets_defaults():
    m = mf.with_defaults(VALID)
    assert mf.validate(VALID) == []
    assert m["port"] == 8080 and m["ui"] is True and m["memory"] == "512m"
    assert m["jobs"][0]["timeout"] == "30m"
    assert m["shared"][0]["rw"] is False


def test_label_round_trip():
    assert mf.from_label(mf.to_label(mf.with_defaults(VALID))) == mf.with_defaults(VALID)


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"spec": "agentos/v2"}, "not supported"),
        ({"spec": "service/v1"}, "expected 'agentos/v1'"),
        ({"id": "GST"}, "id:"),
        ({"id": "-gst"}, "id:"),
        ({"network": None}, "'network' is a required property"),
        ({"egress": None}, "egress: required"),
        ({"unknown": 1}, "Additional properties"),
        ({"secrets": [{"name": "AGENTOS_TOKEN", "description": "x"}]}, "reserved for the platform"),
        ({"secrets": [{"name": "lower", "description": "x"}]}, "secrets.0.name"),
        ({"shared": [{"path": "../etc", "mount": "/x"}]}, "shared.0.path"),
        ({"shared": [{"path": "x", "mount": "/data/x"}]}, "is reserved"),
        ({"jobs": [{"id": "a1", "name": "A"}, {"id": "a1", "name": "B"}]}, "duplicate id"),
        ({"jobs": [{"id": "a1", "name": "A", "schedule": "61 * * * *"}]}, "out of range"),
        ({"jobs": [{"id": "a1", "name": "A", "schedule": "@daily"}]}, "jobs.0.schedule"),
        ({"jobs": [{"id": "a1", "name": "A", "schedule": "0 9 * * MON"}]}, "unsupported value"),
        ({"memory": "512"}, "memory"),
        ({"provides": [{"id": "tx", "description": "a"}, {"id": "tx", "description": "b"}]}, "duplicate id 'tx'"),
        ({"uses": [{"app": "gst", "scope": "tx", "reason": "r"}]}, "connect to itself"),
        ({"uses": [{"app": "bank", "scope": "tx"}]}, "'reason' is a required property"),
    ],
)
def test_invalid_manifests(changes, expected):
    errors = mf.validate(variant(**changes))
    assert any(expected in e for e in errors), errors


def test_network_none_needs_no_egress():
    assert mf.validate(variant(network="none", egress=None)) == []


def test_parse_reports_bad_yaml():
    with pytest.raises(mf.ManifestError, match="invalid YAML"):
        mf.parse("spec: [")


def test_provides_and_uses_defaults():
    m = mf.with_defaults(variant(provides=[{"id": "transactions", "description": "Read transactions"}],
                                 uses=[{"app": "bank-sync", "scope": "transactions", "reason": "GST needs them"}]))
    assert mf.validate(m) == []
    assert m["uses"][0]["optional"] is False
