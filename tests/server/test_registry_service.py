import pytest

from vqec.server.services import registry as registry_service


def test_get_registry_for_category_unknown():
    assert registry_service.get_registry_for_category("unknown") is None


def test_get_category_components_unknown_category():
    assert registry_service.get_category_components("not-a-category") is None


def test_get_component_detail_unknown_category():
    assert registry_service.get_component_detail("not-a-category", "x") is None


def test_get_component_detail_missing_component():
    assert registry_service.get_component_detail("decoders", "nonexistent_decoder_xyz") is None


def test_get_category_components_filters_by_circuit_constructor():
    results = registry_service.get_category_components(
        "decoders",
        circuit_constructor="__no_such_circuit__",
    )
    assert results == []


def test_get_category_components_filters_by_noise_model():
    results = registry_service.get_category_components(
        "decoders",
        noise_model="__no_such_noise__",
    )
    assert results == []


def test_get_category_components_filters_by_runner():
    results = registry_service.get_category_components(
        "decoders",
        runner="stim_runner",
    )
    assert results is not None
    assert all(
        "stim_runner" in comp.compatibility.get("runners", [])
        for comp in results
        if comp.compatibility.get("runners")
    )


def test_get_category_components_filters_exclude_non_matching_runner():
    results = registry_service.get_category_components(
        "decoders",
        runner="__no_such_runner__",
    )
    assert results == []


def test_get_category_components_pagination():
    all_decoders = registry_service.get_category_components("decoders", limit=1000)
    page = registry_service.get_category_components("decoders", limit=1, offset=0)
    assert all_decoders is not None
    assert page is not None
    assert len(page) == 1
    assert page[0].name == all_decoders[0].name
