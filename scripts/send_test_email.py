#!/usr/bin/env python3
"""Manual email-configuration check for Spoolio operators."""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app import create_app
from email_service import send_email_verification, send_password_reset
from models import User


def check_email_configuration():
    """Send verification and reset messages using the configured SMTP service."""
    print("Testing Spoolio email configuration...")

    app = create_app()
    with app.app_context():
        required_vars = [
            "MAIL_SERVER",
            "MAIL_USERNAME",
            "MAIL_PASSWORD",
            "MAIL_DEFAULT_SENDER",
        ]
        missing_vars = [name for name in required_vars if not os.environ.get(name)]

        if missing_vars:
            print(f"Missing email environment variables: {', '.join(missing_vars)}")
            print("Set these variables before running this manual check.")
            return False

        print("Email environment variables are configured")

        test_user = User(username="test_user", email="test@example.com")
        test_user.set_password("testpassword123")

        verification_token = test_user.generate_email_verification_token()
        verification_url = f"https://yourdomain.com/verify-email/{verification_token}"
        if not send_email_verification(test_user, verification_url):
            print("Email verification test failed")
            return False

        reset_token = test_user.generate_password_reset_token()
        reset_url = f"https://yourdomain.com/reset-password/{reset_token}"
        if not send_password_reset(test_user, reset_url):
            print("Password reset test failed")
            return False

        print("All email tests passed")
        return True


if __name__ == "__main__":
    raise SystemExit(0 if check_email_configuration() else 1)
