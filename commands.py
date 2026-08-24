"""Operator-facing Flask CLI commands."""

import click

from blueprints._helpers import validate_email, validate_password, validate_username
from extensions import db
import models


def register_cli(app):
    @app.cli.command('create-user')
    @click.option('--username', prompt=True, help='Unique login name.')
    @click.option('--email', prompt=True, help='Unique email address.')
    @click.option(
        '--password',
        prompt=True,
        hide_input=True,
        confirmation_prompt=True,
        help='Password (prompted securely when omitted).',
    )
    @click.option('--admin', is_flag=True, help='Grant administrator access.')
    @click.option(
        '--unverified',
        is_flag=True,
        help='Require email verification before the first login.',
    )
    def create_user(username, email, password, admin, unverified):
        """Create a verified user without enabling public registration."""
        username = username.strip()
        email = email.strip().lower()
        if not validate_username(username):
            raise click.ClickException(
                'Username must be 3-20 characters, alphanumeric and underscore only'
            )
        if not validate_email(email):
            raise click.ClickException('Invalid email format')
        password_valid, password_error = validate_password(password)
        if not password_valid:
            raise click.ClickException(password_error)
        if models.User.query.filter_by(username=username).first() is not None:
            raise click.ClickException('Username is already registered')
        if models.User.query.filter_by(email=email).first() is not None:
            raise click.ClickException('Email is already registered')

        user = models.User(
            username=username,
            email=email,
            email_verified=not unverified,
            is_admin=admin,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        role = 'administrator' if admin else 'user'
        click.echo(f'Created {role} {username}.')
