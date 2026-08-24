from flask import current_app, render_template_string
from flask_mail import Mail, Message
import os
from time_utils import utc_now_naive

mail = Mail()

def init_mail(app):
    """Initialize Flask-Mail with app configuration"""
    app.config.setdefault('MAIL_SERVER', os.environ.get('MAIL_SERVER', 'smtp.gmail.com'))
    app.config.setdefault('MAIL_PORT', int(os.environ.get('MAIL_PORT', 587)))
    app.config.setdefault('MAIL_USE_TLS', os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true')
    app.config.setdefault('MAIL_USE_SSL', os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true')
    app.config.setdefault('MAIL_USERNAME', os.environ.get('MAIL_USERNAME'))
    app.config.setdefault('MAIL_PASSWORD', os.environ.get('MAIL_PASSWORD'))
    app.config.setdefault('MAIL_DEFAULT_SENDER', os.environ.get('MAIL_DEFAULT_SENDER'))
    app.config.setdefault('MAIL_SUPPRESS_SEND', app.testing)

    mail.init_app(app)

def send_email_verification(user, verification_url):
    """Send email verification email"""
    subject = "Verify your Spoolio account"

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Verify your Spoolio account</title>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
            .container { max-width: 600px; margin: 0 auto; padding: 20px; }
            .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }
            .content { background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }
            .button { display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 20px 0; }
            .footer { text-align: center; margin-top: 30px; color: #666; font-size: 14px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎯 Welcome to Spoolio!</h1>
                <p>Your 3D filament tracking solution</p>
            </div>
            <div class="content">
                <h2>Hi {{ username }},</h2>
                <p>Thank you for signing up for Spoolio! To complete your registration, please verify your email address by clicking the button below:</p>

                <div style="text-align: center;">
                    <a href="{{ verification_url }}" class="button">Verify Email Address</a>
                </div>

                <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #667eea;">{{ verification_url }}</p>

                <p><strong>This link will expire in 24 hours.</strong></p>

                <p>If you didn't create a Spoolio account, you can safely ignore this email.</p>
            </div>
            <div class="footer">
                <p>© 2024 Spoolio. All rights reserved.</p>
                <p>This email was sent to {{ email }}</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_template = """
    Welcome to Spoolio!

    Hi {{ username }},

    Thank you for signing up for Spoolio! To complete your registration, please verify your email address by visiting this link:

    {{ verification_url }}

    This link will expire in 24 hours.

    If you didn't create a Spoolio account, you can safely ignore this email.

    Best regards,
    The Spoolio Team
    """

    html_content = render_template_string(html_template,
                                        username=user.username,
                                        email=user.email,
                                        verification_url=verification_url)
    text_content = render_template_string(text_template,
                                        username=user.username,
                                        verification_url=verification_url)

    msg = Message(subject=subject,
                 recipients=[user.email],
                 html=html_content,
                 body=text_content)

    try:
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send email verification: {e}")
        return False

def send_password_reset(user, reset_url):
    """Send password reset email"""
    subject = "Reset your Spoolio password"

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Reset your Spoolio password</title>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
            .container { max-width: 600px; margin: 0 auto; padding: 20px; }
            .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }
            .content { background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }
            .button { display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 20px 0; }
            .footer { text-align: center; margin-top: 30px; color: #666; font-size: 14px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔐 Password Reset</h1>
                <p>Spoolio Account Security</p>
            </div>
            <div class="content">
                <h2>Hi {{ username }},</h2>
                <p>We received a request to reset your Spoolio password. Click the button below to create a new password:</p>

                <div style="text-align: center;">
                    <a href="{{ reset_url }}" class="button">Reset Password</a>
                </div>

                <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #667eea;">{{ reset_url }}</p>

                <p><strong>This link will expire in 1 hour.</strong></p>

                <p>If you didn't request a password reset, you can safely ignore this email. Your password will remain unchanged.</p>
            </div>
            <div class="footer">
                <p>© 2024 Spoolio. All rights reserved.</p>
                <p>This email was sent to {{ email }}</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_template = """
    Password Reset Request

    Hi {{ username }},

    We received a request to reset your Spoolio password. Click the link below to create a new password:

    {{ reset_url }}

    This link will expire in 1 hour.

    If you didn't request a password reset, you can safely ignore this email. Your password will remain unchanged.

    Best regards,
    The Spoolio Team
    """

    html_content = render_template_string(html_template,
                                        username=user.username,
                                        email=user.email,
                                        reset_url=reset_url)
    text_content = render_template_string(text_template,
                                        username=user.username,
                                        reset_url=reset_url)

    msg = Message(subject=subject,
                 recipients=[user.email],
                 html=html_content,
                 body=text_content)

    try:
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send password reset email: {e}")
        return False


def _owner_notification_recipient():
    recipient = current_app.config.get('WAITLIST_NOTIFICATION_EMAIL')
    return recipient.strip() if isinstance(recipient, str) and recipient.strip() else None


def send_waitlist_confirmation(entry):
    """Send a branded confirmation email to a new waitlist member."""
    subject = "You're on the Spoolio waitlist!"

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Welcome to the Spoolio waitlist</title>
        <style>
            body { font-family: 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #1c1f33; background: #f4f6fb; margin: 0; padding: 0; }
            .container { max-width: 620px; margin: 0 auto; padding: 0 20px 40px; }
            .card { background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 20px 45px rgba(26, 33, 69, 0.12); }
            .header { background: linear-gradient(135deg, #5c6cff 0%, #7b5bff 100%); color: #ffffff; padding: 36px; text-align: center; }
            .header h1 { margin: 0; font-size: 28px; letter-spacing: 0.4px; }
            .header p { margin-top: 10px; font-size: 16px; opacity: 0.92; }
            .content { padding: 36px; }
            .content h2 { margin-top: 0; font-size: 22px; color: #20234a; }
            .pill { display: inline-block; padding: 6px 14px; border-radius: 999px; background: rgba(92, 108, 255, 0.12); color: #5c6cff; font-weight: 600; letter-spacing: 0.2px; margin-bottom: 22px; }
            ul { padding-left: 20px; }
            li { margin-bottom: 12px; }
            .footer { margin-top: 40px; font-size: 14px; color: #6f7591; text-align: center; }
            .footer a { color: #5c6cff; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <div class="header">
                    <h1>Welcome aboard, {{ display_name }}!</h1>
                    <p>The Spoolio waitlist crew is glad to have you 🚀</p>
                </div>
                <div class="content">
                    <span class="pill">You're officially on the list</span>
                    <h2>Here's what happens next:</h2>
                    <ul>
                        <li>We review every signup so the rollout stays smooth for existing makers.</li>
                        <li>You'll be the first to know when the next batch of invites goes out.</li>
                        <li>In the meantime, we'll share behind-the-scenes updates and tips we send the community.</li>
                    </ul>
                    <p>Got a project you'd love Spoolio to help with? Just hit reply and tell us all about it—we read every message.</p>
                    <p style="margin-top: 32px; font-weight: 600; color: #20234a;">Talk soon,<br />The Spoolio team</p>
                </div>
            </div>
            <div class="footer">
                <p>Made with 💜 for makers. © {{ current_year }} Spoolio.</p>
                <p>This email was sent to {{ entry.email }}</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_template = """
    You're on the Spoolio waitlist!

    Hi {{ display_name }},

    Thanks for joining the Spoolio waitlist. We'll review your signup and reach out when the next wave of invites is ready.

    In the meantime, reply to this email if there's something specific you're excited about—we read every response.

    Talk soon,
    The Spoolio team
    """

    display_name = entry.username or entry.email.split('@')[0]
    html_content = render_template_string(html_template,
                                         entry=entry,
                                         display_name=display_name,
                                         current_year=utc_now_naive().year)
    text_content = render_template_string(text_template, display_name=display_name)

    msg = Message(subject=subject,
                  recipients=[entry.email],
                  html=html_content,
                  body=text_content)

    try:
        mail.send(msg)
        return True
    except Exception as exc:
        current_app.logger.error(f"Failed to send waitlist confirmation: {exc}")
        return False


def send_waitlist_notification(entry):
    """Notify the owner about a new waitlist signup."""
    recipient = _owner_notification_recipient()
    if not recipient:
        current_app.logger.warning("WAITLIST_NOTIFICATION_EMAIL not configured; skipping owner alert")
        return False

    subject = f"New Spoolio waitlist signup: {entry.email}"

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>New waitlist signup</title>
        <style>
            body { font-family: Arial, sans-serif; background: #f5f7fb; margin: 0; padding: 30px; color: #1f2430; }
            .container { max-width: 620px; margin: 0 auto; background: #ffffff; border-radius: 12px; box-shadow: 0 18px 35px rgba(31, 44, 64, 0.15); overflow: hidden; }
            .header { background: linear-gradient(135deg, #009efd 0%, #2af598 100%); color: #ffffff; padding: 28px 32px; }
            .header h1 { margin: 0; font-size: 24px; }
            .content { padding: 32px; }
            .details { width: 100%; border-collapse: collapse; }
            .details td { padding: 10px 0; border-bottom: 1px solid #e7eaf3; vertical-align: top; }
            .details td:first-child { width: 160px; font-weight: 600; color: #4a4f63; }
            .footer { padding: 24px 32px; background: #f5f7fb; font-size: 13px; color: #71788a; }
            pre { background: #f0f3fa; padding: 12px; border-radius: 8px; overflow-x: auto; font-size: 13px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>New waitlist signup</h1>
                <p style="margin: 8px 0 0; opacity: 0.9;">{{ entry.created_at.strftime('%Y-%m-%d %H:%M UTC') }}</p>
            </div>
            <div class="content">
                <table class="details">
                    <tr>
                        <td>Email</td>
                        <td>{{ entry.email }}</td>
                    </tr>
                    <tr>
                        <td>Username</td>
                        <td>{{ entry.username or '—' }}</td>
                    </tr>
                    <tr>
                        <td>IP Address</td>
                        <td>{{ entry.ip_address or 'Unknown' }}</td>
                    </tr>
                    <tr>
                        <td>User Agent</td>
                        <td>{{ entry.user_agent or 'Unknown' }}</td>
                    </tr>
                    <tr>
                        <td>Referrer</td>
                        <td>{{ entry.referrer or 'None' }}</td>
                    </tr>
                    <tr>
                        <td>Notes</td>
                        <td>{{ entry.notes or '—' }}</td>
                    </tr>
                </table>
                {% if entry.raw_payload %}
                <h3 style="margin-top: 28px;">Raw payload</h3>
                <pre>{{ entry.raw_payload }}</pre>
                {% endif %}
            </div>
            <div class="footer">
                <p>Notification sent automatically by Spoolio.</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_template = """
    New Spoolio waitlist signup

    Email: {{ entry.email }}
    Username: {{ entry.username or '—' }}
    IP Address: {{ entry.ip_address or 'Unknown' }}
    User Agent: {{ entry.user_agent or 'Unknown' }}
    Referrer: {{ entry.referrer or 'None' }}
    Notes: {{ entry.notes or '—' }}

    {% if entry.raw_payload %}Payload:
    {{ entry.raw_payload }}
    {% endif %}
    """

    html_content = render_template_string(html_template, entry=entry)
    text_content = render_template_string(text_template, entry=entry)

    msg = Message(subject=subject,
                  recipients=[recipient],
                  html=html_content,
                  body=text_content)

    try:
        mail.send(msg)
        return True
    except Exception as exc:
        current_app.logger.error(f"Failed to send waitlist notification: {exc}")
        return False


def send_firmware_release_notification(user, release, download_url, manual_instructions=None, extra_message=None):
    """Send a firmware release announcement to a single user."""
    subject = f"Firmware {release.version} available for {release.hardware_type}"

    manual_block = manual_instructions or ""
    extra_block = extra_message or ""

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Firmware update ready</title>
        <style>
            body { font-family: 'Segoe UI', Arial, sans-serif; background: #f5f7fb; margin: 0; padding: 0; color: #1f2430; }
            .container { max-width: 640px; margin: 0 auto; padding: 24px 16px 48px; }
            .card { background: #ffffff; border-radius: 16px; box-shadow: 0 24px 48px rgba(17, 24, 39, 0.12); overflow: hidden; }
            .header { background: linear-gradient(135deg, #0284c7 0%, #0ea5e9 100%); color: #ffffff; padding: 32px; }
            .header h1 { margin: 0; font-size: 26px; letter-spacing: 0.4px; }
            .content { padding: 32px; }
            .meta { background: #f1f5f9; border-radius: 12px; padding: 16px 20px; margin: 24px 0; }
            .meta p { margin: 6px 0; font-size: 15px; }
            .cta { display: inline-block; margin-top: 12px; background: #0ea5e9; color: #fff; padding: 12px 22px; border-radius: 999px; text-decoration: none; font-weight: 600; }
            pre { background: #0f172a; color: #e2e8f0; padding: 16px; border-radius: 10px; overflow-x: auto; white-space: pre-wrap; line-height: 1.45; }
            .footer { padding: 24px 32px; background: #f8fafc; font-size: 13px; color: #64748b; text-align: center; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <div class="header">
                    <h1>Firmware {{ release.version }} is live</h1>
                    <p style="margin-top: 8px; font-size: 15px;">Ready for your {{ release.hardware_type }} device</p>
                </div>
                <div class="content">
                    <p>Hi {{ user.username or user.email }},</p>
                    <p>We just published a new firmware build for your {{ release.hardware_type }} hardware. You can start an over-the-air update right from the device or grab the binary for manual flashing.</p>
                    {% if release.release_notes %}
                    <div class="meta">
                        <h3 style="margin: 0 0 8px;">Release notes</h3>
                        <p>{{ release.release_notes }}</p>
                    </div>
                    {% endif %}
                    <a href="{{ download_url }}" class="cta">Download signed firmware</a>
                    {% if extra_block %}
                    <div style="margin-top: 24px; padding: 16px 20px; background: #fef9c3; border-radius: 12px; color: #713f12;">
                        {{ extra_block }}
                    </div>
                    {% endif %}
                    {% if manual_block %}
                    <h3 style="margin-top: 32px;">Manual / USB flashing instructions</h3>
                    <pre>{{ manual_block }}</pre>
                    {% endif %}
                    <p style="margin-top: 32px;">The device will automatically check <code>/api/hardware/firmware/latest</code> on each heartbeat. If an OTA update fails or you prefer USB flashing, follow the steps above.</p>
                    <p style="margin-top: 24px;">Happy printing,<br />The Spoolio Team</p>
                </div>
                <div class="footer">
                    <p>Sent {{ current_time.strftime('%Y-%m-%d %H:%M UTC') }}</p>
                    <p>This email was intended for {{ user.email }}.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    text_template = """
    Firmware {{ release.version }} for {{ release.hardware_type }} is ready.

    Download: {{ download_url }}

    {% if release.release_notes %}Release notes:
    {{ release.release_notes }}
    {% endif %}

    {% if extra_block %}
    Additional information:
    {{ extra_block }}
    {% endif %}

    {% if manual_block %}
    Manual / USB flashing instructions:
    {{ manual_block }}
    {% endif %}

    Devices will poll /api/hardware/firmware/latest during heartbeat for OTA updates.

    — Spoolio Team
    """

    html_content = render_template_string(
        html_template,
        user=user,
        release=release,
        download_url=download_url,
        manual_block=manual_block,
        extra_block=extra_block,
        current_time=utc_now_naive()
    )
    text_content = render_template_string(
        text_template,
        release=release,
        download_url=download_url,
        manual_block=manual_block,
        extra_block=extra_block
    )

    msg = Message(
        subject=subject,
        recipients=[user.email],
        html=html_content,
        body=text_content
    )

    try:
        mail.send(msg)
        return True
    except Exception as exc:
        current_app.logger.error(f"Failed to send firmware release notification to {user.email}: {exc}")
        return False
