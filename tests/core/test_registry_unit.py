import warnings
from pathlib import Path

import pytest

from vqec.core.registry import ComponentRegistry, scan_adapters


def test_component_registry_register_and_lookup():
    registry = ComponentRegistry[str]()

    registry.register("alpha", "A")
    assert registry.get("alpha") == "A"
    assert registry.list_names() == ["alpha"]

    with pytest.raises(ValueError, match="already registered"):
        registry.register("alpha", "B")

    registry.register("alpha", "C", overwrite=True)
    assert registry.get("alpha") == "C"

    with pytest.raises(KeyError, match="Unknown component"):
        registry.get("missing")


def test_scan_adapters_missing_path(tmp_path):
    scan_adapters(tmp_path / "does-not-exist")


def test_scan_adapters_warns_on_bad_module(tmp_path):
    bad_module = tmp_path / "broken_adapter.py"
    bad_module.write_text("raise RuntimeError('boom')\n")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        scan_adapters(tmp_path)

    assert any("broken_adapter" in str(w.message) for w in caught)


def test_registry_infers_name_from_class():
    from vqec.core.registry import _Registry

    reg = _Registry("Test")

    class MyWidget:
        pass

    reg.register(MyWidget)
    assert reg.get("my_widget") is MyWidget
