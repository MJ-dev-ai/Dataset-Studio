import pytest

from service.labeling_service import move_in_catalog, normalize_catalog, remove_from_catalog, update_catalog


def test_catalog_edit_preserves_display_order():
    catalog = [(5, "Scratch"), (2, "Dent"), (9, "Crack")]
    assert update_catalog(catalog, 2, 2, "Deep Dent") == [
        (5, "Scratch"), (2, "Deep Dent"), (9, "Crack")
    ]


def test_catalog_can_reorder_without_renumbering_ids():
    catalog = [(5, "Scratch"), (2, "Dent"), (9, "Crack")]
    assert move_in_catalog(catalog, 9, -1) == [(5, "Scratch"), (9, "Crack"), (2, "Dent")]
    assert remove_from_catalog(catalog, 2) == [(5, "Scratch"), (9, "Crack")]


def test_catalog_rejects_duplicate_id_during_edit():
    with pytest.raises(ValueError, match="already exists"):
        update_catalog([(0, "A"), (1, "B")], 1, 0, "B")


def test_normalize_catalog_keeps_first_position_for_duplicates():
    assert normalize_catalog([(3, "Old"), (1, "One"), (3, "New")]) == [(3, "New"), (1, "One")]
