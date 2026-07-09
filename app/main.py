"""
Main blueprint for Comic Book Collection Manager.
Handles the landing page and general application routes.
"""

from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user, login_required
from . import db

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Landing page for the application."""
    return render_template('main/index.html', title='Comic Book Collection Manager')

@main_bp.route('/about')
def about():
    """About page for the application."""
    return render_template('main/about.html', title='About')

@main_bp.route('/contact')
def contact():
    """Contact page for the application."""
    return render_template('main/contact.html', title='Contact')

@main_bp.route('/api/theme', methods=['POST'])
@main_bp.route('/api/dark-mode', methods=['POST'])
@login_required
def update_theme():
    """Update user's theme preference (light, dark, or system)."""
    try:
        data = request.get_json() or {}
        theme = data.get('theme')
        if theme is None and 'dark_mode' in data:
            theme = 'dark' if data.get('dark_mode') else 'light'
        theme = (theme or 'system').lower()
        if theme not in ('light', 'dark', 'system'):
            return jsonify({'success': False, 'message': 'Invalid theme'}), 400

        current_user.set_preferred_theme(theme)
        db.session.commit()

        return jsonify({'success': True, 'theme': current_user.get_preferred_theme()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
