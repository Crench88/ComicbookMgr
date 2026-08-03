"""CRUD routes for comics collection browsing and editing."""

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.orm import defer, with_expression

from .. import db
from ..forms import ComicForm
from ..models import Comic, Series, Tag
from ..services.series_link import apply_series_link
from ..services.tags import normalize_read_status, sync_comic_tags
from . import comics_bp
from .helpers import (
    COMICS_PER_PAGE,
    SERIES_PER_PAGE,
    _annotate_duplicates,
    _apply_comic_filters,
    _apply_form_cover_updates,
    _collection_return_url,
    _comics_for_series_query,
    _filter_series_query,
    _parse_comicvine_issue_id,
    _safe_redirect_target,
    _serialize_comic_for_grid,
    _series_page_for_name,
)


def _credits_from_form(form):
    """Creator fields straight off the form, so new credits need no wiring here."""
    return {field: getattr(form, field).data for field, _ in Comic.CREDIT_FIELDS}


def _catalog_link_kwargs_from_request():
    """Optional catalog/volume ids submitted with the comic form."""
    catalog_raw = (request.form.get('catalog_series_id') or '').strip()
    volume_raw = (request.form.get('comicvine_volume_id') or '').strip()
    catalog_series_id = None
    comicvine_volume_id = None
    if catalog_raw:
        try:
            catalog_series_id = int(catalog_raw)
        except ValueError:
            catalog_series_id = None
    if volume_raw:
        try:
            comicvine_volume_id = int(volume_raw)
        except ValueError:
            comicvine_volume_id = None
    return {
        'catalog_series_id': catalog_series_id,
        'comicvine_volume_id': comicvine_volume_id,
    }


@comics_bp.route('/comics')
@login_required
def index():
    """Display collection as a master-detail series browser."""
    search_query = request.args.get('search', '')
    publisher_filter = request.args.get('publisher', '')
    condition_filter = request.args.get('condition', '')
    genre_filter = request.args.get('genre', '')
    tag_filter = request.args.get('tag', '').strip()
    read_status_filter = request.args.get('read_status', '').strip()
    wishlist_only = request.args.get('wishlist', False, type=bool)
    sort_by = request.args.get('sort', 'issue_number')
    series_page = request.args.get('series_page', 1, type=int)
    comic_page = request.args.get('comic_page', 1, type=int)
    selected_series = request.args.get('series', '')

    filter_kwargs = dict(
        search_query=search_query,
        publisher_filter=publisher_filter,
        condition_filter=condition_filter,
        genre_filter=genre_filter,
        wishlist_only=wishlist_only,
        tag_filter=tag_filter,
        read_status_filter=read_status_filter,
    )

    publishers = db.session.query(Comic.publisher).filter_by(
        user_id=current_user.id
    ).distinct().all()
    publishers = [pub[0] for pub in publishers if pub[0]]
    available_tags = Tag.query.filter_by(user_id=current_user.id).order_by(Tag.name.asc()).all()

    series_pagination = _filter_series_query(
        current_user.id, **filter_kwargs,
    ).paginate(page=series_page, per_page=SERIES_PER_PAGE, error_out=False)

    series_rows = [
        {'name': row.series_name, 'count': row.issue_count}
        for row in series_pagination.items
    ]

    total_comics = db.session.query(func.count(Comic.id)).filter(
        Comic.user_id == current_user.id,
    )
    total_comics = _apply_comic_filters(total_comics, **filter_kwargs).scalar() or 0

    selected_comics = None
    comics_pagination = None
    selected_series_name = None
    selected_series_count = 0

    if series_rows:
        series_names = [row['name'] for row in series_rows]
        if selected_series and selected_series not in series_names:
            count_row = _filter_series_query(
                current_user.id, **filter_kwargs,
            ).filter(
                func.coalesce(
                    func.nullif(func.trim(Comic.series), ''),
                    'Unknown Series',
                ) == selected_series
            ).first()
            if count_row:
                # Jump the sidebar to the page that contains this series.
                needed_page = _series_page_for_name(
                    current_user.id, selected_series, filter_kwargs,
                )
                if needed_page != series_page:
                    args = request.args.to_dict(flat=True)
                    args['series'] = selected_series
                    args['series_page'] = needed_page
                    args['comic_page'] = comic_page
                    return redirect(url_for('comics.index', **args))
            else:
                selected_series = series_names[0]
        elif not selected_series:
            selected_series = series_names[0]

        selected_series_name = selected_series
        selected_series_count = next(
            (row['count'] for row in series_rows if row['name'] == selected_series_name),
            0,
        )
        if selected_series_count == 0:
            count_row = _filter_series_query(
                current_user.id, **filter_kwargs,
            ).filter(
                func.coalesce(
                    func.nullif(func.trim(Comic.series), ''),
                    'Unknown Series',
                ) == selected_series_name
            ).first()
            selected_series_count = count_row.issue_count if count_row else 0

        comics_query = _comics_for_series_query(
            current_user.id, selected_series_name, sort_by=sort_by, **filter_kwargs,
        )
        comics_pagination = comics_query.paginate(
            page=max(1, comic_page),
            per_page=COMICS_PER_PAGE,
            error_out=False,
        )
        if comics_pagination.total and comic_page > comics_pagination.pages:
            args = request.args.to_dict(flat=True)
            args['comic_page'] = comics_pagination.pages
            return redirect(url_for('comics.index', **args))
        _annotate_duplicates(comics_pagination.items)
        selected_comics = comics_pagination.items

    class TotalComics:
        def __init__(self, total):
            self.total = total

    return render_template(
        'comics/index.html',
        title='My Comics',
        comics=TotalComics(total_comics),
        series_rows=series_rows,
        series_pagination=series_pagination,
        selected_series=selected_series_name,
        selected_series_count=selected_series_count,
        selected_comics=selected_comics,
        comics_pagination=comics_pagination,
        search_query=search_query,
        publisher_filter=publisher_filter,
        condition_filter=condition_filter,
        genre_filter=genre_filter,
        wishlist_only=wishlist_only,
        sort_by=sort_by,
        publishers=publishers,
        comics_per_page=COMICS_PER_PAGE,
    )


@comics_bp.route('/comics/series-issues')
@login_required
def series_issues():
    """JSON endpoint for comics in a selected series (AJAX grid refresh)."""
    series_name = request.args.get('series', '').strip()
    if not series_name:
        return jsonify({'error': 'Series name required'}), 400

    search_query = request.args.get('search', '')
    publisher_filter = request.args.get('publisher', '')
    condition_filter = request.args.get('condition', '')
    genre_filter = request.args.get('genre', '')
    tag_filter = request.args.get('tag', '').strip()
    read_status_filter = request.args.get('read_status', '').strip()
    wishlist_only = request.args.get('wishlist', False, type=bool)
    comic_page = request.args.get('comic_page', 1, type=int)
    sort_by = request.args.get('sort', 'issue_number')

    filter_kwargs = dict(
        search_query=search_query,
        publisher_filter=publisher_filter,
        condition_filter=condition_filter,
        genre_filter=genre_filter,
        wishlist_only=wishlist_only,
        tag_filter=tag_filter,
        read_status_filter=read_status_filter,
    )

    comics_query = _comics_for_series_query(
        current_user.id, series_name, sort_by=sort_by, **filter_kwargs,
    )
    pagination = comics_query.paginate(
        page=max(1, comic_page),
        per_page=COMICS_PER_PAGE,
        error_out=False,
    )
    if pagination.total and comic_page > pagination.pages:
        comic_page = pagination.pages
        pagination = comics_query.paginate(
            page=comic_page,
            per_page=COMICS_PER_PAGE,
            error_out=False,
        )
    _annotate_duplicates(pagination.items)

    return jsonify({
        'series': series_name,
        'comics': [_serialize_comic_for_grid(c) for c in pagination.items],
        'pagination': {
            'page': comic_page,
            'pages': pagination.pages or 1,
            'total': pagination.total,
            'per_page': COMICS_PER_PAGE,
            'has_prev': comic_page > 1,
            'has_next': comic_page < pagination.pages,
            'prev_num': comic_page - 1 if comic_page > 1 else None,
            'next_num': comic_page + 1 if comic_page < pagination.pages else None,
        },
    })

@comics_bp.route('/comics/new', methods=['GET', 'POST'])
@login_required
def new():
    """Add a new comic to the collection."""
    form = ComicForm()
    series_options = Series.query.order_by(Series.name.asc(), Series.volume.asc()).all()
    
    if form.validate_on_submit():
        comic = Comic(
            title=form.title.data,  # Individual issue title (e.g., "Worldwide")
            series=(form.series.data or '').strip(),  # Series name (e.g., "The Amazing Spider-Man")
            issue_title=form.title.data,  # Use title field for issue_title
            issue_number=form.issue_number.data,
            publisher=form.publisher.data,
            characters=form.characters.data,
            **_credits_from_form(form),
            teams=form.teams.data,
            story_arc=form.story_arc.data,
            description=form.description.data,
            comicvine_issue_id=_parse_comicvine_issue_id(form.comicvine_issue_id.data),
            comicvine_url=(request.form.get('comicvine_url') or '').strip() or None,
            genre=form.genre.data,
            release_date=form.release_date.data,
            upc=form.upc.data,
            condition=form.condition.data,
            estimated_value=form.estimated_value.data or 0.0,
            notes=form.notes.data,
            user_id=current_user.id
        )
        comic.apply_ownership(
            in_collection=form.in_collection.data,
            is_digital=form.is_digital.data,
        )
        apply_series_link(
            comic,
            form.series.data,
            publisher=form.publisher.data,
            **_catalog_link_kwargs_from_request(),
        )
        comic.read_status = normalize_read_status(form.read_status.data)
        sync_comic_tags(comic, form.tags.data, current_user.id)

        if not _apply_form_cover_updates(comic, form):
            db.session.rollback()
            return render_template(
                'comics/form.html',
                title='Add Comic',
                form=form,
                series_options=series_options,
                comic=None,
            )
        
        try:
            db.session.add(comic)
            db.session.commit()
            flash('Comic added successfully!', 'success')
            return redirect(url_for('comics.index'))
        except Exception as e:
            db.session.rollback()
            flash('Error adding comic. Please try again.', 'danger')
    
    return render_template('comics/form.html', title='Add Comic', form=form, series_options=series_options, comic=None)

@comics_bp.route('/comics/<int:id>')
@login_required
def show(id):
    """Display a specific comic."""
    from ..services.archives import rar_support_error

    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    collection_return_url = _collection_return_url(comic, request.args.get('next', ''))
    return render_template(
        'comics/show.html',
        title=comic.title,
        comic=comic,
        collection_return_url=collection_return_url,
        rar_support_problem=rar_support_error(),
    )

@comics_bp.route('/comics/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit an existing comic."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    collection_return_url = _collection_return_url(comic, request.args.get('next', ''))
    form = ComicForm(obj=comic)
    if request.method == 'GET':
        form.tags.data = comic.get_tags_text()
        form.read_status.data = normalize_read_status(comic.read_status)
        form.in_collection.data = bool(comic.in_collection)
        form.is_digital.data = bool(comic.is_digital or comic.has_digital_file())
    series_options = Series.query.order_by(Series.name.asc(), Series.volume.asc()).all()
    
    if form.validate_on_submit():
        comic.title = form.title.data  # Individual issue title (e.g., "Worldwide")
        comic.issue_title = form.title.data  # Use title field for issue_title
        comic.issue_number = form.issue_number.data
        comic.publisher = form.publisher.data
        apply_series_link(
            comic,
            form.series.data,
            publisher=form.publisher.data,
            **_catalog_link_kwargs_from_request(),
        )
        comic.read_status = normalize_read_status(form.read_status.data)
        sync_comic_tags(comic, form.tags.data, current_user.id)
        comic.characters = form.characters.data
        for field, value in _credits_from_form(form).items():
            setattr(comic, field, value)
        comic.teams = form.teams.data
        comic.story_arc = form.story_arc.data
        comic.description = form.description.data
        comic.comicvine_issue_id = _parse_comicvine_issue_id(form.comicvine_issue_id.data)
        if 'comicvine_url' in request.form:
            comic.comicvine_url = request.form.get('comicvine_url', '').strip() or None
        comic.genre = form.genre.data
        comic.release_date = form.release_date.data
        comic.upc = form.upc.data
        comic.condition = form.condition.data
        comic.estimated_value = form.estimated_value.data or 0.0
        comic.notes = form.notes.data
        comic.apply_ownership(
            in_collection=form.in_collection.data,
            is_digital=form.is_digital.data,
        )
        
        if not _apply_form_cover_updates(comic, form):
            db.session.rollback()
            return render_template(
                'comics/form.html',
                title='Edit Comic',
                form=form,
                comic=comic,
                series_options=series_options,
                collection_return_url=collection_return_url,
            )
        
        try:
            db.session.commit()
            flash('Comic updated successfully!', 'success')
            return redirect(url_for('comics.show', id=comic.id, next=collection_return_url))
        except Exception as e:
            db.session.rollback()
            flash('Error updating comic. Please try again.', 'danger')
    
    return render_template(
        'comics/form.html',
        title='Edit Comic',
        form=form,
        comic=comic,
        series_options=series_options,
        collection_return_url=collection_return_url,
    )

@comics_bp.route('/comics/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Delete a comic from the collection."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    
    try:
        from ..services.digital_files import delete_comic_digital_assets

        delete_comic_digital_assets(comic)
        db.session.delete(comic)
        db.session.commit()
        flash('Comic deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting comic {id}: {e}")
        flash('Error deleting comic. Please try again.', 'danger')
    
    next_url = _safe_redirect_target(request.form.get('next'))
    return redirect(next_url or url_for('comics.index'))


@comics_bp.route('/comics/<int:id>/estimated-value', methods=['POST'])
@login_required
def update_estimated_value(id):
    """Save an estimated value looked up from market comps on the show page."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    payload = request.get_json(silent=True) or {}
    raw_value = payload.get('estimated_value')
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'A numeric estimated value is required.'}), 400
    if value < 0:
        return jsonify({'success': False, 'error': 'Estimated value cannot be negative.'}), 400

    comic.estimated_value = round(value, 2)
    db.session.commit()
    return jsonify({
        'success': True,
        'estimated_value': comic.estimated_value,
        'formatted_value': comic.get_formatted_value(),
    })


@comics_bp.route('/comics/<int:id>/ownership', methods=['POST'])
@login_required
def update_ownership(id):
    """Update In Collection / Digital ownership sliders from the show page."""
    comic = Comic.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    payload = request.get_json(silent=True) or {}
    if 'in_collection' not in payload and 'is_digital' not in payload:
        return jsonify({'success': False, 'error': 'Ownership fields are required.'}), 400

    in_collection = payload.get('in_collection', comic.in_collection)
    is_digital = payload.get('is_digital', comic.is_digital)
    # Keep Digital on when a file is attached so the UI cannot lie about presence.
    if comic.has_digital_file():
        is_digital = True

    comic.apply_ownership(in_collection=in_collection, is_digital=is_digital)
    db.session.commit()
    return jsonify({
        'success': True,
        'in_collection': comic.in_collection,
        'is_digital': comic.is_digital,
        'is_wishlist': comic.is_wishlist,
        'digital_active': comic.digital_active,
        'tags': comic.ownership_status_tags(),
    })


@comics_bp.route('/comics/wishlist')
@login_required
def wishlist():
    """Display wishlist items."""
    page = request.args.get('page', 1, type=int)
    wishlist_comics = Comic.query.filter_by(
        user_id=current_user.id, is_wishlist=True
    ).options(
        defer(Comic.cover_image),
        defer(Comic.additional_covers),
        with_expression(
        Comic.cover_available,
        db.or_(Comic.cover_image_path.isnot(None), Comic.cover_image.isnot(None)),
    ),
    ).order_by(Comic.title, Comic.issue_number).paginate(
        page=page, per_page=12, error_out=False
    )
    
    return render_template('comics/wishlist.html',
                         title='Wishlist',
                         comics=wishlist_comics)
