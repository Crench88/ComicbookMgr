"""
Dashboard blueprint for Comic Book Collection Manager.
Handles the main dashboard with statistics and overview.
"""

from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import defer, with_expression
from . import db
from .models import Comic
from .services.characters import top_characters_for_user
from .services.reading_queue import dashboard_reading_queues

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def index():
    """Main dashboard page with collection statistics."""
    # Get basic statistics
    total_comics = Comic.query.filter_by(user_id=current_user.id, is_wishlist=False).count()
    wishlist_count = Comic.query.filter_by(user_id=current_user.id, is_wishlist=True).count()
    total_value = db.session.query(func.sum(Comic.estimated_value)).filter_by(
        user_id=current_user.id, is_wishlist=False
    ).scalar() or 0.0
    
    # Get top publishers
    top_publishers = db.session.query(
        Comic.publisher, func.count(Comic.id).label('count')
    ).filter_by(user_id=current_user.id, is_wishlist=False).group_by(
        Comic.publisher
    ).order_by(func.count(Comic.id).desc()).limit(5).all()
    
    top_characters = top_characters_for_user(current_user.id)
    
    # Get recent additions
    recent_comics = Comic.query.filter_by(
        user_id=current_user.id, is_wishlist=False
    ).options(
        defer(Comic.cover_image),
        defer(Comic.additional_covers),
        with_expression(
            Comic.cover_available,
            db.or_(Comic.cover_image_path.isnot(None), Comic.cover_image.isnot(None)),
        ),
    ).order_by(Comic.created_at.desc()).limit(9).all()
    
    # Get condition distribution
    condition_stats = db.session.query(
        Comic.condition, func.count(Comic.id).label('count')
    ).filter_by(user_id=current_user.id, is_wishlist=False).group_by(
        Comic.condition
    ).all()

    queues = dashboard_reading_queues(current_user.id)

    return render_template('dashboard/index.html',
                         title='Dashboard',
                         total_comics=total_comics,
                         wishlist_count=wishlist_count,
                         total_value=total_value,
                         top_publishers=top_publishers,
                         top_characters=top_characters,
                         recent_comics=recent_comics,
                         continue_reading=queues['continue_reading'],
                         unread_digital=queues['unread_digital'],
                         next_in_series=queues['next_in_series'],
                         condition_stats=condition_stats)

@dashboard_bp.route('/profile')
@login_required
def profile():
    """User profile and settings page."""
    return render_template('dashboard/profile.html', title='Profile')
