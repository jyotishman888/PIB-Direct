import numpy as np
import pytest

from pib_agent.similarity.embeddings import embed_text

pytestmark = pytest.mark.slow


def test_embed_text_returns_unit_float32_vector():
    vector = embed_text("India crosses 300 GW of non-fossil fuel power capacity.")

    assert vector.dtype == np.float32
    assert vector.ndim == 1
    assert np.isclose(np.linalg.norm(vector), 1.0, atol=1e-4)


def test_similar_texts_score_higher_than_unrelated_texts():
    renewable_a = embed_text(
        "India crosses 300 GW of non-fossil fuel power generation capacity, "
        "driven by solar and wind expansion."
    )
    renewable_b = embed_text(
        "Ministry of New and Renewable Energy announces record solar capacity "
        "addition under the PM Surya Ghar scheme."
    )
    unrelated = embed_text(
        "Vice-President launches Har Ghar Tiranga Abhiyan in Andaman and Nicobar Islands."
    )

    sim_related = float(renewable_a @ renewable_b)
    sim_unrelated = float(renewable_a @ unrelated)

    assert sim_related > sim_unrelated
