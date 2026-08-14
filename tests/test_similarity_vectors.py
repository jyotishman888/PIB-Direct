import numpy as np

from pib_agent.similarity.vectors import bytes_to_vector, vector_to_bytes


def test_vector_round_trips_through_bytes():
    original = np.array([0.1, -0.2, 0.3, 1.0, -1.0], dtype=np.float32)

    data = vector_to_bytes(original)
    restored = bytes_to_vector(data)

    assert data == original.tobytes()
    assert restored.dtype == np.float32
    np.testing.assert_array_equal(restored, original)


def test_vector_to_bytes_casts_to_float32():
    original = np.array([0.1, 0.2], dtype=np.float64)

    data = vector_to_bytes(original)
    restored = bytes_to_vector(data)

    assert restored.dtype == np.float32
    assert len(data) == 2 * 4  # two float32 values
