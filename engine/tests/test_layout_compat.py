from __future__ import annotations

import pytest


@pytest.mark.contract
def test_generation_and_config_shims_match_runtime_exports() -> None:
    from quote.config import default_activation_config as legacy_default_activation_config
    from quote.config import default_sae_config as legacy_default_sae_config
    from quote.generation import GenerationResult as legacy_generation_result
    from quote.generation import generate as legacy_generate
    from quote.runtime.config import default_activation_config, default_sae_config
    from quote.runtime.generation import GenerationResult, generate

    assert legacy_default_activation_config is default_activation_config
    assert legacy_default_sae_config is default_sae_config
    assert legacy_generation_result is GenerationResult
    assert legacy_generate is generate


@pytest.mark.contract
def test_activation_shims_match_storage_exports() -> None:
    from quote.activations import ActivationQueries as legacy_activation_queries
    from quote.activations import ActivationStore as legacy_activation_store
    from quote.activations import FeatureActivationRow as legacy_feature_activation_row
    from quote.activations.queries import ActivationQueries as legacy_activation_queries_mod
    from quote.activations.schema import FeatureActivationRow as legacy_feature_activation_row_mod
    from quote.activations.store import ActivationStore as legacy_activation_store_mod
    from quote.storage.activations import ActivationQueries, ActivationStore, FeatureActivationRow

    assert legacy_activation_queries is ActivationQueries
    assert legacy_activation_store is ActivationStore
    assert legacy_feature_activation_row is FeatureActivationRow
    assert legacy_activation_queries_mod is ActivationQueries
    assert legacy_activation_store_mod is ActivationStore
    assert legacy_feature_activation_row_mod is FeatureActivationRow
