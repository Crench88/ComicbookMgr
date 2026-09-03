"""
Idle session timeout for authenticated users.

Applies to every account, including admins. A session is expired when no
authenticated request has been made for IDLE_TIMEOUT_SECONDS (default 30 minutes).
"""

from datetime import datetime, timezone

from flask import current_app, flash, jsonify, redirect, request, session, url_for
from flask_login import current_user, logout_user

LAST_ACTIVITY_KEY = 'last_activity'
DEFAULT_IDLE_TIMEOUT_SECONDS = 30 * 60


def utc_timestamp():
    """Current UTC time as a POSIX timestamp."""
    return datetime.now(timezone.utc).timestamp()


def idle_timeout_seconds():
    """Configured idle window in seconds."""
    return int(current_app.config.get('IDLE_TIMEOUT_SECONDS', DEFAULT_IDLE_TIMEOUT_SECONDS))


def mark_activity():
    """Record that the current user was active just now."""
    session[LAST_ACTIVITY_KEY] = utc_timestamp()
    session.modified = True


def session_is_idle():
    """Return True when last activity is older than the idle window."""
    last = session.get(LAST_ACTIVITY_KEY)
    if last is None:
        return False
    try:
        last_ts = float(last)
    except (TypeError, ValueError):
        return True
    return (utc_timestamp() - last_ts) > idle_timeout_seconds()


def _wants_json():
    if request.is_json:
        return True
    best = request.accept_mimetypes.best
    return best == 'application/json'


def expire_idle_session():
    """Log the current user out and clear idle-tracking state."""
    logout_user()
    session.pop(LAST_ACTIVITY_KEY, None)
    session.modified = True
    flash(
        'You were logged out because your session was idle for more than 30 minutes.',
        'info',
    )


def enforce_idle_timeout():
    """
    Flask before_request hook: expire idle sessions for all authenticated users.

    Missing last_activity (for example a test that only sets _user_id) is treated
    as a fresh session and stamped now, so existing callers keep working.
    """
    if request.endpoint in ('static', 'auth.logout'):
        return None
    if not current_user.is_authenticated:
        return None

    if session_is_idle():
        expire_idle_session()
        if _wants_json():
            return jsonify(error='Session expired due to inactivity'), 401
        return redirect(url_for('auth.login'))

    mark_activity()
    return None
