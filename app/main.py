"""
Main blueprint for Comic Book Collection Manager.
Handles the landing page and general application routes.
"""

from flask import Blueprint, render_template
from flask_login import current_user

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
