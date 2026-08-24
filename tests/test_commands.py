"""Operator CLI coverage."""


def test_create_user_command_creates_verified_admin(app):
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=[
            'create-user',
            '--username', 'operator',
            '--email', 'OPERATOR@example.com',
            '--password', 'OperatorPass1',
            '--admin',
        ],
    )
    assert result.exit_code == 0, result.output
    assert 'Created administrator operator.' in result.output

    import models

    with app.app_context():
        user = models.User.query.one()
        assert user.email == 'operator@example.com'
        assert user.email_verified is True
        assert user.is_admin is True
        assert user.check_password('OperatorPass1') is True


def test_create_user_command_rejects_duplicates_and_weak_passwords(app):
    runner = app.test_cli_runner()
    weak = runner.invoke(
        args=[
            'create-user',
            '--username', 'operator',
            '--email', 'operator@example.com',
            '--password', 'weak',
        ],
    )
    assert weak.exit_code != 0

    created = runner.invoke(
        args=[
            'create-user',
            '--username', 'operator',
            '--email', 'operator@example.com',
            '--password', 'OperatorPass1',
        ],
    )
    assert created.exit_code == 0

    duplicate = runner.invoke(
        args=[
            'create-user',
            '--username', 'operator',
            '--email', 'other@example.com',
            '--password', 'OperatorPass2',
        ],
    )
    assert duplicate.exit_code != 0
    assert 'Username is already registered' in duplicate.output
