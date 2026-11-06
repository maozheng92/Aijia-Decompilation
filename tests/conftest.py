"""Load protocol modules without importing Home Assistant."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = ROOT / "custom_components" / "hisense_e7n"
PKG_NAME = "hisense_e7n_proto"


def _ensure_pkg() -> types.ModuleType:
    if PKG_NAME in sys.modules:
        return sys.modules[PKG_NAME]
    pkg = types.ModuleType(PKG_NAME)
    pkg.__path__ = [str(PKG_DIR)]  # type: ignore[attr-defined]
    pkg.__package__ = PKG_NAME
    sys.modules[PKG_NAME] = pkg
    return pkg


def load_proto(name: str):
    _ensure_pkg()
    full = f"{PKG_NAME}.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, PKG_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    module.__package__ = PKG_NAME
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def proto_const():
    return load_proto("const")


@pytest.fixture(scope="session")
def proto_credentials(proto_const):
    return load_proto("credentials")


@pytest.fixture(scope="session")
def proto_keys():
    return load_proto("keys")


@pytest.fixture(scope="session")
def proto_topics(proto_credentials):
    return load_proto("topics")


@pytest.fixture(scope="session")
def proto_client(proto_topics, proto_keys, proto_const):
    load_proto("certs_util")
    return load_proto("tv_client")


@pytest.fixture(scope="session")
def proto_power():
    return load_proto("power")
