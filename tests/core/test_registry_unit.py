import warnings
from pathlib import Path

import pytest

from vqec.core.registry import ComponentRegistry


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


def test_registry_infers_name_from_class():
    from vqec.core.registry import _Registry

    reg = _Registry("Test")

    class MyWidget:
        pass

    reg.register(MyWidget)
    assert reg.get("my_widget") is MyWidget
