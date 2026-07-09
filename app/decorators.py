"""Route decorators for authorization."""

from functools import wraps

from flask import abort, flash
from flask_login import current_user, login_required


def admin_required(view):
    """Require an authenticated user with admin privileges."""

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not getattr(current_user, 'is_admin', False):
            flash('Admin access required.', 'danger')
            abort(403)
        return view(*args, **kwargs)

    return wrapped
