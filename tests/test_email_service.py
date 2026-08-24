"""Outbound email configuration boundaries."""

import datetime
from types import SimpleNamespace


def _waitlist_entry():
    return SimpleNamespace(
        email='maker@example.com',
        username='maker',
        ip_address=None,
        user_agent=None,
        referrer=None,
        notes=None,
        raw_payload=None,
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )


def test_waitlist_owner_alert_has_no_personal_fallback(app, monkeypatch):
    from email_service import mail, send_waitlist_notification

    app.config['WAITLIST_NOTIFICATION_EMAIL'] = None
    monkeypatch.setattr(
        mail,
        'send',
        lambda _message: (_ for _ in ()).throw(
            AssertionError('mail should not be sent without a configured recipient')
        ),
    )

    with app.app_context():
        assert send_waitlist_notification(_waitlist_entry()) is False


def test_waitlist_owner_alert_uses_only_the_configured_recipient(app, monkeypatch):
    from email_service import mail, send_waitlist_notification

    sent = []
    app.config['WAITLIST_NOTIFICATION_EMAIL'] = 'owner@example.com'
    monkeypatch.setattr(mail, 'send', sent.append)

    with app.app_context():
        assert send_waitlist_notification(_waitlist_entry()) is True

    assert len(sent) == 1
    assert sent[0].recipients == ['owner@example.com']
