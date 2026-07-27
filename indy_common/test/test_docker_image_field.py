import pytest
from indy_common.types import DockerImageField


@pytest.fixture
def field():
    return DockerImageField()


def test_valid_full_registry_image_tag(field):
    assert field.validate('ghcr.io/hyperledger/indy-node:latest') is None


def test_valid_image_tag(field):
    assert field.validate('indy-node:1.0.0') is None


def test_valid_image_with_digest(field):
    assert field.validate('indy-node@sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789') is None


def test_valid_registry_port(field):
    assert field.validate('registry:5000/indy-node:latest') is None


def test_valid_simple_image(field):
    assert field.validate('alpine') is None


def test_valid_multi_namespace(field):
    assert field.validate('ghcr.io/hyperledger/indy-node') is None


def test_invalid_empty_string(field):
    assert field.validate('') is not None


def test_invalid_whitespace(field):
    assert field.validate('indy node:latest') is not None


def test_invalid_starts_with_slash(field):
    assert field.validate('/indy-node:latest') is not None


def test_invalid_special_chars(field):
    assert field.validate('indy-node:latest!') is not None
