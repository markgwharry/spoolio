"""Authentication and waitlist API coverage."""

import datetime
import json
import threading
from concurrent.futures import ThreadPoolExecutor


def _login(client, username, password="Aa123456"):
    return client.post(
        "/api/login",
        json={"username": username, "password": password},
    )


def test_health_reports_database_readiness(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "checks": {"database": True},
    }


def test_registration_status_defaults_to_waitlist(client):
    response = client.get('/api/registration')
    assert response.status_code == 200
    assert response.get_json() == {
        'mode': 'waitlist',
        'action': 'waitlist',
        'registration_enabled': False,
        'waitlist_enabled': True,
        'password_required': False,
        'setup_code_required': False,
    }


def test_first_user_registration_creates_one_verified_admin(app, client):
    app.config['REGISTRATION_MODE'] = 'first-user'

    before = client.get('/api/registration')
    assert before.get_json() == {
        'mode': 'first-user',
        'action': 'create-owner',
        'registration_enabled': True,
        'waitlist_enabled': False,
        'password_required': True,
        'setup_code_required': True,
    }

    missing_password = client.post(
        '/api/register',
        json={
            'username': 'owner',
            'email': 'owner@example.com',
            'registration_token': app.config['REGISTRATION_TOKEN'],
        },
    )
    assert missing_password.status_code == 400

    invalid_code = client.post(
        '/api/register',
        json={
            'username': 'owner',
            'email': 'owner@example.com',
            'password': 'OwnerPass1',
            'registration_token': 'wrong-setup-code',
        },
    )
    assert invalid_code.status_code == 403

    created = client.post(
        '/api/register',
        json={
            'username': 'owner',
            'email': 'owner@example.com',
            'password': 'OwnerPass1',
            'registration_token': app.config['REGISTRATION_TOKEN'],
        },
    )
    assert created.status_code == 201
    assert created.get_json()['account_created'] is True
    assert created.get_json()['user']['is_admin'] is True

    import models

    with app.app_context():
        owner = models.User.query.one()
        assert owner.email_verified is True
        assert owner.is_admin is True
        assert owner.check_password('OwnerPass1') is True
        assert models.RegistrationBootstrap.query.count() == 1
        assert models.WaitlistEntry.query.count() == 0

    login = _login(client, 'owner', 'OwnerPass1')
    assert login.status_code == 200

    after = client.get('/api/registration')
    assert after.get_json()['action'] == 'closed'
    assert after.get_json()['registration_enabled'] is False

    second = client.post(
        '/api/register',
        json={
            'username': 'second-owner',
            'email': 'second@example.com',
            'password': 'OwnerPass2',
            'registration_token': app.config['REGISTRATION_TOKEN'],
        },
    )
    assert second.status_code == 403
    with app.app_context():
        assert models.User.query.count() == 1


def test_first_user_mode_stays_closed_after_owner_is_deleted(app, client):
    app.config['REGISTRATION_MODE'] = 'first-user'
    created = client.post(
        '/api/register',
        json={
            'username': 'owner',
            'email': 'owner@example.com',
            'password': 'OwnerPass1',
            'registration_token': app.config['REGISTRATION_TOKEN'],
        },
    )
    assert created.status_code == 201

    from extensions import db
    import models

    with app.app_context():
        db.session.delete(models.User.query.one())
        db.session.commit()

    assert client.get('/api/registration').get_json()['action'] == 'closed'
    replacement = client.post(
        '/api/register',
        json={
            'username': 'replacement',
            'email': 'replacement@example.com',
            'password': 'OwnerPass2',
            'registration_token': app.config['REGISTRATION_TOKEN'],
        },
    )
    assert replacement.status_code == 403


def test_first_user_claim_is_atomic_across_concurrent_clients(app, monkeypatch):
    app.config['REGISTRATION_MODE'] = 'first-user'

    import models

    claim_held = threading.Event()
    release_claim = threading.Event()
    original_set_password = models.User.set_password

    def hold_winning_request(user, password):
        claim_held.set()
        assert release_claim.wait(timeout=2)
        return original_set_password(user, password)

    monkeypatch.setattr(models.User, 'set_password', hold_winning_request)

    def submit(username):
        with app.test_client() as concurrent_client:
            return concurrent_client.post(
                '/api/register',
                json={
                    'username': username,
                    'email': f'{username}@example.com',
                    'password': 'OwnerPass1',
                    'registration_token': app.config['REGISTRATION_TOKEN'],
                },
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(submit, 'owner_one')
        assert claim_held.wait(timeout=2)
        second = executor.submit(submit, 'owner_two')
        release_claim.set()
        statuses = sorted((first.result(timeout=5), second.result(timeout=5)))

    assert statuses == [201, 409]
    with app.app_context():
        assert models.User.query.count() == 1
        assert models.User.query.one().is_admin is True
        assert models.RegistrationBootstrap.query.count() == 1


def test_closed_registration_mode_rejects_submissions(app, client):
    app.config['REGISTRATION_MODE'] = 'closed'
    status = client.get('/api/registration').get_json()
    assert status['action'] == 'closed'
    assert status['waitlist_enabled'] is False

    response = client.post(
        '/api/register',
        json={
            'username': 'unused',
            'email': 'unused@example.com',
            'password': 'UnusedPass1',
        },
    )
    assert response.status_code == 403


def test_register_creates_only_a_sanitized_waitlist_entry(
    app,
    client,
    monkeypatch,
):
    sent = []
    monkeypatch.setattr(
        "blueprints.auth.send_waitlist_confirmation",
        lambda entry: sent.append(("confirmation", entry.email)) or True,
    )
    monkeypatch.setattr(
        "blueprints.auth.send_waitlist_notification",
        lambda entry: sent.append(("owner", entry.email)) or True,
    )

    response = client.post(
        "/api/register",
        json={
            "username": "waitlisted_user",
            "email": "waitlisted@example.com",
            "password": "ValidPass1",
            "project": "open source scale",
        },
        headers={
            "X-Forwarded-For": "203.0.113.5, 10.0.0.1",
            "User-Agent": "Spoolio test client",
            "Referer": "https://example.com/scales",
        },
    )

    assert response.status_code == 202
    assert response.get_json() == {
        "msg": (
            "Thanks for your interest in Spoolio. If this address can be added "
            "to the waitlist, we will be in touch."
        ),
        "waitlisted": True,
    }
    assert sent == [
        ("confirmation", "waitlisted@example.com"),
        ("owner", "waitlisted@example.com"),
    ]

    from extensions import db
    import models

    with app.app_context():
        assert models.User.query.count() == 0
        entry = models.WaitlistEntry.query.one()
        assert entry.username == "waitlisted_user"
        assert entry.ip_address == "203.0.113.5"
        assert entry.user_agent == "Spoolio test client"
        assert entry.referrer == "https://example.com/scales"
        payload = json.loads(entry.raw_payload)
        assert payload["project"] == "open source scale"
        assert "password" not in payload

    repeat = client.post(
        "/api/register",
        json={
            "username": "updated_name",
            "email": "waitlisted@example.com",
            "password": "ValidPass1",
            "project": "updated details",
        },
        headers={"X-Forwarded-For": "198.51.100.8"},
    )
    assert repeat.status_code == 202
    assert repeat.get_json() == response.get_json()

    with app.app_context():
        assert models.WaitlistEntry.query.count() == 1
        entry = models.WaitlistEntry.query.one()
        assert entry.ip_address == "198.51.100.8"
        assert json.loads(entry.raw_payload)["project"] == "updated details"
        db.session.expire_all()


def test_register_validates_input_and_does_not_create_a_user(
    app,
    client,
    user_factory,
):
    existing = user_factory(username="existing", email="existing@example.com")

    assert client.post("/api/register", json={}).status_code == 400
    assert client.post(
        "/api/register",
        json={"username": "x", "email": "invalid", "password": "short"},
    ).status_code == 400

    response = client.post(
        "/api/register",
        json={
            "username": existing.username,
            "email": "new@example.com",
            "password": "ValidPass1",
        },
    )
    assert response.status_code == 202

    same_email = client.post(
        "/api/register",
        json={
            "username": "unused_name",
            "email": existing.email,
            "password": "ValidPass1",
        },
    )
    assert same_email.status_code == 202
    assert same_email.get_json() == response.get_json()

    import models

    with app.app_context():
        assert models.WaitlistEntry.query.count() == 1
        entry = models.WaitlistEntry.query.one()
        assert entry.username == existing.username
        assert entry.email == "new@example.com"


def test_auth_routes_reject_wrong_json_types_without_server_errors(client):
    responses = [
        client.post(
            "/api/register",
            json={"username": 123, "email": ["bad"], "password": {"bad": True}},
        ),
        client.post("/api/login", json={"username": "name", "password": 123}),
        client.post("/api/forgot-password", json={"email": 123}),
        client.post("/api/reset-password/not-a-token", json={"password": 123}),
        client.post("/api/resend-verification", json={"email": ["bad"]}),
    ]
    assert all(response.status_code == 400 for response in responses)
    assert all(response.is_json for response in responses)


def test_login_success_failure_verification_and_lockout(
    app,
    client,
    user_factory,
):
    alice = user_factory(username="login-alice", email="login-alice@example.com")
    unverified = user_factory(
        username="unverified",
        email="unverified@example.com",
        email_verified=False,
    )

    missing = client.post("/api/login", json={})
    assert missing.status_code == 400
    malformed = client.post(
        "/api/login",
        data="{not-json",
        content_type="application/json",
    )
    assert malformed.status_code == 400

    response = _login(client, alice.username)
    assert response.status_code == 200
    body = response.get_json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["id"] == alice.id

    response = _login(client, unverified.username)
    assert response.status_code == 401
    assert response.get_json()["email_verification_required"] is True

    for _ in range(5):
        response = _login(client, alice.username, "WrongPass1")
        assert response.status_code == 401

    from extensions import db
    import models

    with app.app_context():
        stored = db.session.get(models.User, alice.id)
        assert stored.failed_login_attempts == 5
        assert stored.locked_until is not None

    locked = _login(client, alice.username)
    assert locked.status_code == 429

    with app.app_context():
        stored = db.session.get(models.User, alice.id)
        stored.locked_until = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
        db.session.commit()

    recovered = _login(client, alice.username)
    assert recovered.status_code == 200
    with app.app_context():
        stored = db.session.get(models.User, alice.id)
        assert stored.failed_login_attempts == 0
        assert stored.locked_until is None


def test_refresh_and_protected_routes_keep_user_identities_isolated(
    client,
    user_factory,
):
    alice = user_factory(username="token-alice", email="token-alice@example.com")
    bob = user_factory(username="token-bob", email="token-bob@example.com")

    alice_login = _login(client, alice.username).get_json()
    bob_login = _login(client, bob.username).get_json()

    alice_protected = client.get(
        "/api/protected",
        headers={"Authorization": f"Bearer {alice_login['access_token']}"},
    )
    bob_protected = client.get(
        "/api/protected",
        headers={"Authorization": f"Bearer {bob_login['access_token']}"},
    )
    assert alice_protected.get_json()["msg"].startswith("Hello, token-alice!")
    assert bob_protected.get_json()["msg"].startswith("Hello, token-bob!")

    refreshed = client.post(
        "/api/refresh",
        headers={"Authorization": f"Bearer {alice_login['refresh_token']}"},
    )
    assert refreshed.status_code == 200
    assert refreshed.get_json()["access_token"]

    wrong_token_type = client.post(
        "/api/refresh",
        headers={"Authorization": f"Bearer {alice_login['access_token']}"},
    )
    assert wrong_token_type.status_code == 422


def test_logout_revokes_all_user_tokens_without_affecting_other_users(
    app,
    client,
    user_factory,
):
    alice = user_factory(username="logout-alice", email="logout-alice@example.com")
    bob = user_factory(username="logout-bob", email="logout-bob@example.com")
    alice_login = _login(client, alice.username).get_json()
    bob_login = _login(client, bob.username).get_json()

    logged_out = client.post(
        "/api/logout",
        headers={"Authorization": f"Bearer {alice_login['refresh_token']}"},
    )
    assert logged_out.status_code == 200

    assert client.get(
        "/api/protected",
        headers={"Authorization": f"Bearer {alice_login['access_token']}"},
    ).status_code == 401
    assert client.post(
        "/api/refresh",
        headers={"Authorization": f"Bearer {alice_login['refresh_token']}"},
    ).status_code == 401
    assert client.post(
        "/api/refresh",
        headers={"Authorization": f"Bearer {bob_login['refresh_token']}"},
    ).status_code == 200

    with app.app_context():
        from extensions import db
        import models

        assert db.session.get(models.User, alice.id).token_version == 1
        assert db.session.get(models.User, bob.id).token_version == 0


def test_email_verification_token_round_trip(app, client, user_factory):
    user = user_factory(
        username="verify-me",
        email="verify-me@example.com",
        email_verified=False,
    )

    from extensions import db
    import models

    with app.app_context():
        stored = db.session.get(models.User, user.id)
        token = stored.generate_email_verification_token()
        db.session.commit()

    response = client.get(f"/api/verify-email/{token}")
    assert response.status_code == 200

    with app.app_context():
        stored = db.session.get(models.User, user.id)
        assert stored.email_verified is True
        assert stored.email_verification_token is None

    assert client.get(f"/api/verify-email/{token}").status_code == 400


def test_expired_verification_and_reset_tokens_are_rejected(
    app,
    client,
    user_factory,
):
    user = user_factory(
        username="expired-tokens",
        email="expired-tokens@example.com",
        email_verified=False,
    )

    from extensions import db
    import models

    with app.app_context():
        stored = db.session.get(models.User, user.id)
        verification_token = stored.generate_email_verification_token()
        stored.email_verification_expires = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
        )
        reset_token = stored.generate_password_reset_token()
        stored.password_reset_expires = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
        )
        db.session.commit()

    assert client.get(f"/api/verify-email/{verification_token}").status_code == 400
    assert client.post(
        f"/api/reset-password/{reset_token}",
        json={"password": "NewValid2"},
    ).status_code == 400


def test_password_reset_is_generic_and_token_is_single_use(
    app,
    client,
    monkeypatch,
    user_factory,
):
    user = user_factory(username="reset-me", email="reset-me@example.com")
    pre_reset_login = _login(client, user.username).get_json()
    sent_urls = []
    monkeypatch.setattr(
        "blueprints.auth.send_password_reset",
        lambda _user, url: sent_urls.append(url) or True,
    )

    known = client.post("/api/forgot-password", json={"email": user.email})
    unknown = client.post(
        "/api/forgot-password",
        json={"email": "nobody@example.com"},
    )
    assert known.status_code == 200
    assert unknown.status_code == 200
    assert known.get_json() == unknown.get_json()
    assert len(sent_urls) == 1

    from extensions import db
    import models

    with app.app_context():
        token = db.session.get(models.User, user.id).password_reset_token

    weak = client.post(
        f"/api/reset-password/{token}",
        json={"password": "weak"},
    )
    assert weak.status_code == 400

    reset = client.post(
        f"/api/reset-password/{token}",
        json={"password": "NewValid2"},
    )
    assert reset.status_code == 200
    assert client.post(
        "/api/refresh",
        headers={"Authorization": f"Bearer {pre_reset_login['refresh_token']}"},
    ).status_code == 401
    assert _login(client, user.username, "Aa123456").status_code == 401
    assert _login(client, user.username, "NewValid2").status_code == 200
    assert client.post(
        f"/api/reset-password/{token}",
        json={"password": "AnotherValid3"},
    ).status_code == 400


def test_resend_verification_uses_a_generic_response(
    client,
    monkeypatch,
    user_factory,
):
    unverified = user_factory(
        username="needs-verification",
        email="needs-verification@example.com",
        email_verified=False,
    )
    verified = user_factory(
        username="already-verified",
        email="already-verified@example.com",
    )
    sent = []
    monkeypatch.setattr(
        "blueprints.auth.send_email_verification",
        lambda user, url: sent.append((user.id, url)) or True,
    )

    responses = [
        client.post("/api/resend-verification", json={"email": unverified.email}),
        client.post("/api/resend-verification", json={"email": verified.email}),
        client.post("/api/resend-verification", json={"email": "unknown@example.com"}),
    ]
    assert all(response.status_code == 200 for response in responses)
    assert len({response.get_json()["msg"] for response in responses}) == 1
    assert len(sent) == 1
    assert sent[0][0] == unverified.id


def test_login_rate_limit_emits_headers(rate_limited_client):
    responses = [
        rate_limited_client.post(
            "/api/login",
            json={"username": "missing-user", "password": "WrongPass1"},
        )
        for _ in range(11)
    ]
    assert all(response.status_code == 401 for response in responses[:10])
    assert responses[10].status_code == 429
    assert responses[0].headers["X-RateLimit-Limit"] == "10"
    assert "X-RateLimit-Remaining" in responses[0].headers
