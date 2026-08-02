from mgost.settings.settings import Settings


def test_round_trip_preserves_values():
    settings = Settings(project_id=7, project_name='Test')
    assert Settings.from_dict(settings.to_dict()).project_id == 7
    assert Settings.from_dict(settings.to_dict()).project_name == 'Test'


def test_unset_project_serialises_to_nothing():
    assert Settings().to_dict() == {}


def test_legacy_keys_are_ignored():
    """Existing .mgost/settings.json files carry md_path and docx_path.
    from_dict does cls(**dictionary), so they must be filtered or load
    raises TypeError."""
    legacy = {
        'project_id': 7,
        'project_name': 'Test',
        'md_path': 'None',
        'docx_path': 'output.docx',
    }

    settings = Settings.from_dict(legacy)

    assert settings.project_id == 7
    assert not hasattr(settings, 'md_path')
