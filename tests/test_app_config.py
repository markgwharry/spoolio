"""Application factory configuration contracts."""

import pytest


def test_invalid_registration_mode_is_rejected():
    from app import create_app

    with pytest.raises(ValueError, match='REGISTRATION_MODE'):
        create_app({'REGISTRATION_MODE': 'open-to-everyone'})


def test_first_user_mode_requires_a_strong_setup_token():
    from app import create_app

    with pytest.raises(ValueError, match='REGISTRATION_TOKEN'):
        create_app({
            'REGISTRATION_MODE': 'first-user',
            'REGISTRATION_TOKEN': 'too-short',
        })
