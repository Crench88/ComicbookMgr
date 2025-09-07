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

@main_bp.route('/api/dark-mode', methods=['POST'])
@login_required
def update_dark_mode():
    """Update user's dark mode preference."""
    try:
        data = request.get_json()
        dark_mode = data.get('dark_mode', False)
        
        # Update user's dark mode preference
        current_user.dark_mode_preference = dark_mode
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Dark mode preference updated'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
