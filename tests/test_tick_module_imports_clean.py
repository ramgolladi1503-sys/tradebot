def test_tick_dataset_import_has_no_side_effects():
    import models.tick_dataset as tick_dataset

    assert tick_dataset.__name__ == "models.tick_dataset"
