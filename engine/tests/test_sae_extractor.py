from __future__ import annotations

from pathlib import Path
import sys
import types

import pytest

pytestmark = [pytest.mark.unit]

from quote.backends.interface import SAEConfig
from quote.interp.sae_extract import MinimalSAEExtractor


def _write_fake_sae_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "cfg.json").write_text("{}", encoding="utf-8")
    (path / "sae_weights.safetensors").write_text("fake", encoding="utf-8")


def test_sae_extractor_prefers_local_sae_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}
    _write_fake_sae_dir(tmp_path)

    class _FakeSAE:
        @staticmethod
        def load_from_disk(path: str, device: str = "cpu"):
            calls["load_from_disk"] = (path, device)
            return object()

        @staticmethod
        def from_pretrained(release: str, sae_id: str, device: str = "cpu"):
            calls["from_pretrained"] = (release, sae_id, device)
            return object(), {}, None

    monkeypatch.setitem(sys.modules, "sae_lens", types.SimpleNamespace(SAE=_FakeSAE))
    cfg = SAEConfig(
        enabled=True,
        mode="inline",
        sae_id="llama_scope_lxr_8x",
        layer=16,
        top_k=8,
        sae_local_path=str(tmp_path),
    )
    extractor = MinimalSAEExtractor(cfg)
    sae = extractor._ensure_loaded()  # noqa: SLF001 - unit test for loader wiring
    assert sae is not None
    assert "load_from_disk" in calls
    assert "from_pretrained" not in calls


def test_sae_extractor_uses_layer_subdir_when_needed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: dict[str, object] = {}
    base = tmp_path / "local-saes"
    nested = base / "l16r_8x"
    _write_fake_sae_dir(nested)

    class _FakeSAE:
        @staticmethod
        def load_from_disk(path: str, device: str = "cpu"):
            calls["load_from_disk"] = (path, device)
            return object()

        @staticmethod
        def from_pretrained(release: str, sae_id: str, device: str = "cpu"):
            calls["from_pretrained"] = (release, sae_id, device)
            return object(), {}, None

    monkeypatch.setitem(sys.modules, "sae_lens", types.SimpleNamespace(SAE=_FakeSAE))
    cfg = SAEConfig(
        enabled=True,
        mode="inline",
        sae_id="llama_scope_lxr_8x",
        layer=16,
        top_k=8,
        sae_local_path=str(base),
    )
    extractor = MinimalSAEExtractor(cfg)
    _ = extractor._ensure_loaded()  # noqa: SLF001 - unit test for loader wiring
    assert "load_from_disk" in calls
    loaded_path, _device = calls["load_from_disk"]  # type: ignore[misc]
    assert Path(str(loaded_path)).name == "l16r_8x"


def test_sae_extractor_falls_back_to_hub_when_local_path_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: dict[str, object] = {}

    class _FakeSAE:
        @staticmethod
        def load_from_disk(path: str, device: str = "cpu"):
            calls["load_from_disk"] = (path, device)
            return object()

        @staticmethod
        def from_pretrained(release: str, sae_id: str, device: str = "cpu"):
            calls["from_pretrained"] = (release, sae_id, device)
            return object(), {}, None

    monkeypatch.setitem(sys.modules, "sae_lens", types.SimpleNamespace(SAE=_FakeSAE))
    cfg = SAEConfig(
        enabled=True,
        mode="inline",
        sae_id="llama_scope_lxr_8x",
        layer=16,
        top_k=8,
        sae_local_path=str(tmp_path / "does-not-exist"),
    )
    extractor = MinimalSAEExtractor(cfg)
    sae = extractor._ensure_loaded()  # noqa: SLF001 - unit test for loader wiring
    assert sae is not None
    assert "from_pretrained" in calls
    assert "load_from_disk" not in calls
