"""
Email utilities for Comic Book Collection Manager.
Handles sending password reset emails and other notifications.
"""

from flask import current_app, render_template
from flask_mail import Message
from . import mail

def send_password_reset_email(user, token):
    """
    Send password reset email to user.
    
    Args:
        user: User object
        token: Password reset token
    """
    try:
        msg = Message(
            subject='Reset Your Password - Comic Book Collection Manager',
            recipients=[user.email],
            html=render_template('auth/email/reset_password.html', 
                               user=user, token=token),
            body=render_template('auth/email/reset_password.txt', 
                               user=user, token=token)
        )
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f'Failed to send password reset email: {e}')
        return False

def send_password_changed_email(user):
    """
    Send confirmation email when password is changed.
    
    Args:
        user: User object
    """
    try:
        msg = Message(
            subject='Password Changed - Comic Book Collection Manager',
            recipients=[user.email],
            html=render_template('auth/email/password_changed.html', user=user),
            body=render_template('auth/email/password_changed.txt', user=user)
        )
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f'Failed to send password changed email: {e}')
        return False
