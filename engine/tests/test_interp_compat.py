from __future__ import annotations

import pytest


@pytest.mark.contract
def test_legacy_and_unified_interp_imports_match() -> None:
    from quote.features import MinimalSAEExtractor as legacy_minimal_from_pkg
    from quote.features.neuronpedia import NeuronpediaClient as legacy_neuronpedia
    from quote.features.sae_extract import MinimalSAEExtractor as legacy_minimal
    from quote.interp import (
        FeatureExtractor,
        MinimalSAEExtractor,
        NeuronpediaClient,
        SAELoader,
        get_feature_extractor,
        get_sae_loader,
    )
    from quote.interpretability import (
        FeatureExtractor as legacy_feature_extractor_from_pkg,
        get_feature_extractor as legacy_get_feature_extractor_from_pkg,
    )
    from quote.interpretability.feature_extractor import (
        FeatureExtractor as legacy_feature_extractor,
        get_feature_extractor as legacy_get_feature_extractor,
    )
    from quote.interpretability.sae_loader import (
        SAELoader as legacy_sae_loader,
        get_sae_loader as legacy_get_sae_loader,
    )

    assert legacy_minimal is MinimalSAEExtractor
    assert legacy_minimal_from_pkg is MinimalSAEExtractor
    assert legacy_neuronpedia is NeuronpediaClient
    assert legacy_feature_extractor is FeatureExtractor
    assert legacy_feature_extractor_from_pkg is FeatureExtractor
    assert legacy_get_feature_extractor is get_feature_extractor
    assert legacy_get_feature_extractor_from_pkg is get_feature_extractor
    assert legacy_sae_loader is SAELoader
    assert legacy_get_sae_loader is get_sae_loader
