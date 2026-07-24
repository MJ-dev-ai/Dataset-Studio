import numpy as np

from service.augmentation_service import BoundedImageCache


def test_bounded_image_cache_evicts_oldest_array(tmp_path):
    cache = BoundedImageCache(max_bytes=20)
    first_path, second_path = tmp_path / "first.png", tmp_path / "second.png"
    cache.put(first_path, np.zeros((3, 3), dtype=np.uint8))
    second = np.zeros((4, 4), dtype=np.uint8)
    cache.put(second_path, second)
    assert cache.get(first_path) is None
    assert cache.get(second_path) is second
    assert cache.size_bytes <= 20
