"""
Comics blueprint for Comic Book Collection Manager.
Handles comic book CRUD operations, search, and filtering.
"""

import os
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from PIL import Image
from . import db
from .models import Comic
from .forms import ComicForm, SearchForm

comics_bp = Blueprint('comics', __name__)

def save_cover_image(file):
    """Save uploaded cover image and return filename."""
    if file and file.filename:
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        
        # Save original file
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        
        # Ensure upload directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        try:
            file.save(filepath)
            print(f"File saved successfully: {filepath}")
        except Exception as e:
            print(f"Error saving file: {e}")
            return None
        
        # Create thumbnail
        try:
            with Image.open(filepath) as img:
                img.thumbnail((300, 300))
                thumb_filename = f"thumb_{filename}"
                thumb_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], thumb_filename)
                img.save(thumb_filepath)
                print(f"Thumbnail created: {thumb_filepath}")
        except Exception as e:
            print(f"Error creating thumbnail: {e}")
        
        return filename
    return None

@comics_bp.route('/comics')
@login_required
def index():
    """Display all comics with search and filtering."""
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '')
    publisher_filter = request.args.get('publisher', '')
    condition_filter = request.args.get('condition', '')
    genre_filter = request.args.get('genre', '')
    wishlist_only = request.args.get('wishlist', False, type=bool)
    
    # Build query
    query = Comic.query.filter_by(user_id=current_user.id)
    
    if search_query:
        query = query.filter(
            db.or_(
                Comic.title.ilike(f'%{search_query}%'),
                Comic.characters.ilike(f'%{search_query}%'),
                Comic.publisher.ilike(f'%{search_query}%')
            )
        )
    
    if publisher_filter:
        query = query.filter(Comic.publisher == publisher_filter)
    
    if condition_filter:
        query = query.filter(Comic.condition == condition_filter)
    
    if genre_filter:
        query = query.filter(Comic.genre.ilike(f'%{genre_filter}%'))
    
    if wishlist_only:
        query = query.filter(Comic.is_wishlist == True)
    
    # Get unique publishers for filter dropdown
    publishers = db.session.query(Comic.publisher).filter_by(
        user_id=current_user.id
    ).distinct().all()
    publishers = [pub[0] for pub in publishers if pub[0]]
    
    comics = query.order_by(Comic.title, Comic.issue_number).paginate(
        page=page, per_page=12, error_out=False
    )
    
    return render_template('comics/index.html',
                         title='My Comics',
                         comics=comics,
                         search_query=search_query,
                         publisher_filter=publisher_filter,
                         condition_filter=condition_filter,
                         genre_filter=genre_filter,
                         wishlist_only=wishlist_only,
                         publishers=publishers)

@comics_bp.route('/comics/new', methods=['GET', 'POST'])
@login_required
def new():
    """Add a new comic to the collection."""
    form = ComicForm()
    
    if form.validate_on_submit():
        comic = Comic(
            title=form.title.data,
            issue_number=form.issue_number.data,
            publisher=form.publisher.data,
            characters=form.characters.data,
            genre=form.genre.data,
            release_date=form.release_date.data,
            condition=form.condition.data,
            estimated_value=form.estimated_value.data or 0.0,
            notes=form.notes.data,
            is_wishlist=form.is_wishlist.data,
            user_id=current_user.id
        )
        
        # Handle cover image upload
        if form.cover_image.data:
            filename = save_cover_image(form.cover_image.data)
            if filename:
                comic.cover_image = filename
        
        try:
            db.session.add(comic)
            db.session.commit()
            flash('Comic added successfully!', 'success')
            return redirect(url_for('comics.index'))
        except Exception as e:
            db.session.rollback()
            flash('Error adding comic. Please try again.', 'danger')
    
    return render_template('comics/form.html', title='Add Comic', form=form)

@comics_bp.route('/comics/<int:id>')
@login_required
def show(id):
    """Display a specific comic."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    return render_template('comics/show.html', title=comic.title, comic=comic)

@comics_bp.route('/comics/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit an existing comic."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    form = ComicForm(obj=comic)
    
    if form.validate_on_submit():
        comic.title = form.title.data
        comic.issue_number = form.issue_number.data
        comic.publisher = form.publisher.data
        comic.characters = form.characters.data
        comic.genre = form.genre.data
        comic.release_date = form.release_date.data
        comic.condition = form.condition.data
        comic.estimated_value = form.estimated_value.data or 0.0
        comic.notes = form.notes.data
        comic.is_wishlist = form.is_wishlist.data
        
        # Handle cover image upload
        if form.cover_image.data:
            filename = save_cover_image(form.cover_image.data)
            if filename:
                # Delete old image if exists
                if comic.cover_image:
                    old_file = os.path.join(current_app.config['UPLOAD_FOLDER'], comic.cover_image)
                    if os.path.exists(old_file):
                        os.remove(old_file)
                comic.cover_image = filename
        
        try:
            db.session.commit()
            flash('Comic updated successfully!', 'success')
            return redirect(url_for('comics.show', id=comic.id))
        except Exception as e:
            db.session.rollback()
            flash('Error updating comic. Please try again.', 'danger')
    
    return render_template('comics/form.html', title='Edit Comic', form=form, comic=comic)

@comics_bp.route('/comics/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Delete a comic from the collection."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    
    try:
        # Delete cover image if exists
        if comic.cover_image:
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], comic.cover_image)
            if os.path.exists(file_path):
                os.remove(file_path)
        
        db.session.delete(comic)
        db.session.commit()
        flash('Comic deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting comic. Please try again.', 'danger')
    
    return redirect(url_for('comics.index'))

@comics_bp.route('/comics/export')
@login_required
def export():
    """Export collection to CSV."""
    import csv
    from io import StringIO
    
    comics = Comic.query.filter_by(user_id=current_user.id, is_wishlist=False).all()
    
    si = StringIO()
    cw = csv.writer(si)
    
    # Write header
    cw.writerow(['Title', 'Issue Number', 'Publisher', 'Characters', 'Genre', 
                 'Release Date', 'Condition', 'Estimated Value', 'Notes'])
    
    # Write data
    for comic in comics:
        cw.writerow([
            comic.title,
            comic.issue_number,
            comic.publisher,
            comic.characters or '',
            comic.genre or '',
            comic.release_date.strftime('%Y-%m-%d') if comic.release_date else '',
            comic.condition or '',
            comic.estimated_value or 0.0,
            comic.notes or ''
        ])
    
    output = si.getvalue()
    si.close()
    
    return send_file(
        StringIO(output),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'comic_collection_{datetime.now().strftime("%Y%m%d")}.csv'
    )

@comics_bp.route('/comics/wishlist')
@login_required
def wishlist():
    """Display wishlist items."""
    page = request.args.get('page', 1, type=int)
    wishlist_comics = Comic.query.filter_by(
        user_id=current_user.id, is_wishlist=True
    ).order_by(Comic.title, Comic.issue_number).paginate(
        page=page, per_page=12, error_out=False
    )
    
    return render_template('comics/wishlist.html',
                         title='Wishlist',
                         comics=wishlist_comics)

@comics_bp.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded cover images."""
    from flask import send_from_directory
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)
