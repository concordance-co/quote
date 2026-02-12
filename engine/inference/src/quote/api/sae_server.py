"""
Standalone SAE (Sparse Autoencoder) feature extraction server.

Provides a minimal FastAPI app for SAE feature extraction and
Claude-powered analysis, independent of the MAX Engine inference server.
"""

from __future__ import annotations

import logging
import os

from fastapi import Body, FastAPI, HTTPException

logger = logging.getLogger(__name__)


def create_sae_app() -> FastAPI:
    """Create and return a standalone FastAPI app for SAE feature extraction."""

    app = FastAPI(title="SAE Analysis Server")

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "sae-analysis"}

    @app.post("/extract_features")
    async def extract_features(body: dict = Body(...)):
        """
        Extract SAE feature activations for a token sequence.

        Body format:
        {
            "tokens": [1, 2, 3, ...],
            "top_k": 20,
            "layer": 16,
            "injection_positions": [5, 10]
        }
        """
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")

        tokens = body.get("tokens")
        if not isinstance(tokens, list) or not tokens:
            raise HTTPException(
                status_code=400,
                detail="tokens must be a non-empty list of token IDs",
            )

        try:
            tokens = [int(t) for t in tokens]
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400, detail="tokens must be a list of integers"
            )

        top_k = body.get("top_k", 20)
        layer = body.get("layer", 16)
        injection_positions = body.get("injection_positions")

        try:
            from quote.interp import get_feature_extractor

            hf_model_id = "meta-llama/Llama-3.1-8B-Instruct"
            sae_id = "llama_scope_lxr_8x"

            extractor = get_feature_extractor(
                model_id=hf_model_id,
                sae_id=sae_id,
                layer=layer,
            )

            timeline = extractor.extract_timeline(tokens, top_k=top_k)

            result = {"feature_timeline": timeline}

            if injection_positions and isinstance(injection_positions, list):
                try:
                    injection_positions = [int(p) for p in injection_positions]
                    comparisons = extractor.extract_comparison(
                        tokens,
                        injection_positions,
                        top_k=top_k,
                    )
                    result["comparisons"] = comparisons.get("comparisons", [])
                except (ValueError, TypeError):
                    pass

            return result

        except ImportError as e:
            logger.error(f"Feature extraction dependencies not available: {e}")
            raise HTTPException(
                status_code=501,
                detail="Feature extraction not available. Required: transformers, sae-lens",
            )
        except Exception as e:
            logger.error(f"Feature extraction failed: {e}")
            raise HTTPException(
                status_code=500, detail=f"Feature extraction failed: {str(e)}"
            )

    @app.post("/analyze_features")
    async def analyze_features(body: dict = Body(...)):
        """
        Analyze SAE feature activations using Claude.

        Fetches Neuronpedia descriptions for top features and asks Claude
        to interpret the activation patterns.

        Body format:
        {
            "feature_timeline": [...],
            "injection_positions": [5, 10],
            "context": "User injected 'test' at position 5",
            "layer": 16
        }
        """
        import httpx
        import anthropic

        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")

        timeline = body.get("feature_timeline")
        if not timeline or not isinstance(timeline, list):
            raise HTTPException(
                status_code=400, detail="feature_timeline is required"
            )

        injection_positions = body.get("injection_positions", [])
        context = body.get("context", "")
        layer = body.get("layer", 16)

        # Collect unique top features across all positions
        feature_counts: dict[int, float] = {}
        for entry in timeline:
            for feat in entry.get("top_features", [])[:5]:
                fid = feat.get("id")
                act = feat.get("activation", 0)
                if fid is not None:
                    feature_counts[fid] = max(feature_counts.get(fid, 0), act)

        # Get top 20 most activated features overall
        top_features = sorted(feature_counts.items(), key=lambda x: -x[1])[:20]

        # Fetch Neuronpedia descriptions for these features
        async def fetch_neuronpedia_description(feature_id: int) -> str:
            url = f"https://www.neuronpedia.org/api/feature/llama3.1-8b/{layer}-llamascope-res-32k/{feature_id}"
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        explanation = data.get("explanations", [{}])
                        if explanation:
                            return explanation[0].get("description", "No description")
                        return data.get("description", "No description available")
            except Exception as e:
                logger.warning(
                    f"Failed to fetch Neuronpedia description for {feature_id}: {e}"
                )
            return "Description unavailable"

        # Fetch descriptions for top features
        feature_descriptions = {}
        for fid, activation in top_features:
            desc = await fetch_neuronpedia_description(fid)
            feature_descriptions[fid] = {
                "activation": activation,
                "description": desc,
            }

        # Build the analysis prompt
        timeline_summary = []
        for entry in timeline:
            pos = entry.get("position", 0)
            token = entry.get("token_str", "?")
            is_injection = pos in injection_positions
            top_feats = entry.get("top_features", [])[:3]
            feat_strs = [f"#{f['id']}({f['activation']:.1f})" for f in top_feats]
            marker = " [INJECTED]" if is_injection else ""
            timeline_summary.append(
                f"Pos {pos}: '{token}'{marker} -> {', '.join(feat_strs)}"
            )

        feature_desc_text = "\n".join(
            [
                f"Feature #{fid}: {info['description']} (max activation: {info['activation']:.1f})"
                for fid, info in feature_descriptions.items()
            ]
        )

        prompt = f"""Analyze these SAE (Sparse Autoencoder) feature activations from a language model generation.

## Context
{context if context else "User ran token injection experiment in a playground."}

## Top Features Detected (with Neuronpedia descriptions)
{feature_desc_text}

## Token-by-Token Timeline
{chr(10).join(timeline_summary[:50])}
{"..." if len(timeline_summary) > 50 else ""}

## Injection Positions
{injection_positions if injection_positions else "None specified"}

## Your Task
Provide a concise analysis (2-3 paragraphs) of:
1. What interpretable patterns you see in the feature activations
2. How the injected tokens (if any) affected the model's internal representations
3. Any interesting or surprising feature activations

Focus on insights that would help someone understand what the model is "thinking" during this generation."""

        # Call Claude API
        try:
            client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            analysis = message.content[0].text
        except Exception as e:
            logger.error(f"Claude API call failed: {e}")
            raise HTTPException(
                status_code=500, detail=f"Analysis failed: {str(e)}"
            )

        return {
            "analysis": analysis,
            "top_features": [
                {
                    "id": fid,
                    "activation": info["activation"],
                    "description": info["description"],
                }
                for fid, info in feature_descriptions.items()
            ],
        }

    return app
