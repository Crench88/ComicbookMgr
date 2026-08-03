"""
Administrative routes for managing comic metadata such as canonical series lists.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import current_user
from .decorators import admin_required
from sqlalchemy.exc import IntegrityError
from flask_wtf.csrf import generate_csrf
import csv
from io import StringIO

from . import db
from .forms import SeriesForm, SeriesIssueForm, SeriesIssueUploadForm
from .models import Series, SeriesIssue, Comic, User
from .services.comicvine import (
    parse_comicvine_volume_id,
    fetch_volume_issues_for_import,
    fetch_volume_detail,
)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/series', methods=['GET', 'POST'])
@admin_required
def series_index():
    """View and manage the canonical series list used throughout the app."""
    form = SeriesForm()
    series_list = Series.query.order_by(Series.name.asc(), Series.volume.asc()).all()

    if form.validate_on_submit():
        name = form.name.data.strip()
        volume = form.volume.data.strip() if form.volume.data else None
        publisher = form.publisher.data.strip() if form.publisher.data else None
        date_range = form.date_range.data.strip() if form.date_range.data else None
        notes = form.notes.data.strip() if form.notes.data else None

        new_series = Series(
            name=name,
            volume=volume,
            publisher=publisher,
            date_range=date_range,
            notes=notes
        )

        db.session.add(new_series)
        try:
            db.session.commit()
            flash('Series added to your canonical list.', 'success')
            return redirect(url_for('admin.series_index'))
        except IntegrityError:
            db.session.rollback()
            flash('This series and volume already exists in your list.', 'warning')

    return render_template('admin/series.html', form=form, series_list=series_list, csrf_token=generate_csrf())


@admin_bp.route('/series/<int:series_id>/delete', methods=['POST'])
@admin_required
def delete_series(series_id):
    """Remove a series entry."""
    series = Series.query.get_or_404(series_id)
    db.session.delete(series)
    db.session.commit()
    flash('Series removed from your list.', 'success')
    return redirect(url_for('admin.series_index'))


@admin_bp.route('/series/issues', methods=['GET', 'POST'])
@admin_required
def series_issues():
    """Manage canonical issue data for a series."""
    series_list = Series.query.order_by(Series.name.asc(), Series.volume.asc()).all()
    series_choices = [(s.id, s.display_name) for s in series_list]

    selected_series_id = request.args.get('series_id', type=int)

    issue_form = SeriesIssueForm()
    issue_form.series_id.choices = series_choices
    upload_form = SeriesIssueUploadForm()
    upload_form.series_id.choices = series_choices

    if selected_series_id:
        issue_form.series_id.data = selected_series_id
        upload_form.series_id.data = selected_series_id

    issues = []
    if selected_series_id:
        series = db.session.get(Series, selected_series_id)
        if series:
            issues = sorted(series.issues, key=lambda issue: issue.sort_key)

    if request.method == 'POST' and request.form.get('action') == 'add_selected':
        selected_ids = request.form.getlist('selected_issues')
        if not selected_ids:
            flash('No issues selected to add.', 'warning')
            return redirect(url_for('admin.series_issues', series_id=selected_series_id or ''))

        try:
            selected_ids = [int(i) for i in selected_ids]
        except ValueError:
            flash('Invalid selection received.', 'danger')
            return redirect(url_for('admin.series_issues', series_id=selected_series_id or ''))

        issues_to_add = SeriesIssue.query.filter(SeriesIssue.id.in_(selected_ids)).all()
        added = 0
        skipped = 0

        for issue in issues_to_add:
            series = issue.series
            if not series:
                skipped += 1
                continue

            existing = Comic.query.filter_by(
                user_id=current_user.id,
                series=series.display_name,
                issue_number=issue.issue_number
            ).first()
            if existing:
                skipped += 1
                continue

            release_date = None
            if issue.cover_date:
                from datetime import datetime
                parsed = issue.cover_date.strip()
                parsed_formats = ['%Y-%m-%d', '%B %Y', '%b %Y', '%Y']
                for fmt in parsed_formats:
                    try:
                        dt = datetime.strptime(parsed, fmt)
                        if fmt == '%Y':
                            dt = dt.replace(month=1, day=1)
                        release_date = dt.date()
                        break
                    except ValueError:
                        continue

            story_note = issue.story_arc or ''
            if issue.writer:
                story_note = f"{story_note} Writer: {issue.writer}".strip()
            if issue.artist:
                story_note = f"{story_note} Artist: {issue.artist}".strip()

            comic = Comic(
                title=issue.title or series.display_name,
                series=series.display_name,
                series_id=series.id,
                issue_title=issue.title or series.display_name,
                issue_number=issue.issue_number,
                publisher=series.publisher or '',
                characters=issue.featured_characters or '',
                genre='',
                release_date=release_date,
                notes=story_note,
                user_id=current_user.id
            )
            db.session.add(comic)
            added += 1

        db.session.commit()
        if added:
            flash(f'Added {added} issue{"s" if added != 1 else ""} to your comics.', 'success')
        if skipped and not added:
            flash('Selected issues were already in your collection.', 'info')
        elif skipped:
            flash(f'{skipped} issue{"s" if skipped != 1 else ""} skipped (already in your comics).', 'warning')

        return redirect(url_for('admin.series_issues', series_id=selected_series_id or ''))

    if issue_form.submit_add.data and issue_form.validate_on_submit():
        series_id = issue_form.series_id.data
        new_issue = SeriesIssue(
            series_id=series_id,
            issue_number=issue_form.issue_number.data.strip(),
            title=issue_form.title.data.strip() if issue_form.title.data else None,
            cover_date=issue_form.cover_date.data.strip() if issue_form.cover_date.data else None,
            featured_characters=issue_form.featured_characters.data.strip() if issue_form.featured_characters.data else None,
            writer=issue_form.writer.data.strip() if issue_form.writer.data else None,
            artist=issue_form.artist.data.strip() if issue_form.artist.data else None,
            story_arc=issue_form.story_arc.data.strip() if issue_form.story_arc.data else None,
        )
        db.session.add(new_issue)
        db.session.commit()
        flash('Issue added to the series list.', 'success')
        return redirect(url_for('admin.series_issues', series_id=series_id))

    if upload_form.submit_upload.data and upload_form.validate_on_submit():
        series_id = upload_form.series_id.data
        file_storage = upload_form.file.data
        try:
            file_storage.stream.seek(0)
            stream = StringIO(file_storage.stream.read().decode('utf-8-sig'))
            reader = csv.DictReader(stream)
            expected_headers = [
                'Issue Number',
                'Title',
                'Cover Date',
                'Featured Characters',
                'Writer',
                'Artist',
                'Story Arc'
            ]
            actual_headers = [h.strip() for h in (reader.fieldnames or [])]
            if actual_headers != expected_headers:
                flash('CSV headers do not match expected format.', 'danger')
            else:
                added_count = 0
                for row in reader:
                    issue = SeriesIssue(
                        series_id=series_id,
                        issue_number=(row.get('Issue Number') or '').strip(),
                        title=(row.get('Title') or '').strip() or None,
                        cover_date=(row.get('Cover Date') or '').strip() or None,
                        featured_characters=(row.get('Featured Characters') or '').strip() or None,
                        writer=(row.get('Writer') or '').strip() or None,
                        artist=(row.get('Artist') or '').strip() or None,
                        story_arc=(row.get('Story Arc') or '').strip() or None,
                    )
                    if issue.issue_number:
                        db.session.add(issue)
                        added_count += 1
                db.session.commit()
                flash(f'Uploaded {added_count} issues to the series.', 'success')
                return redirect(url_for('admin.series_issues', series_id=series_id))
        except UnicodeDecodeError:
            flash('Unable to decode CSV. Ensure it is UTF-8 encoded.', 'danger')

    return render_template(
        'admin/series_issues.html',
        series_list=series_list,
        issue_form=issue_form,
        upload_form=upload_form,
        issues=issues,
        selected_series_id=selected_series_id,
        csrf_token=generate_csrf()
    )


@admin_bp.route('/series/issues/<int:issue_id>/delete', methods=['POST'])
@admin_required
def delete_series_issue(issue_id):
    """Delete a canonical issue record."""
    issue = SeriesIssue.query.get_or_404(issue_id)
    series_id = issue.series_id
    db.session.delete(issue)
    db.session.commit()
    flash('Issue removed from the series list.', 'success')
    return redirect(url_for('admin.series_issues', series_id=series_id))


@admin_bp.route('/series/<int:series_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_series(series_id):
    """Edit an existing series entry."""
    series = Series.query.get_or_404(series_id)
    form = SeriesForm(obj=series)

    if form.validate_on_submit():
        series.name = form.name.data.strip()
        series.volume = form.volume.data.strip() if form.volume.data else None
        series.publisher = form.publisher.data.strip() if form.publisher.data else None
        series.date_range = form.date_range.data.strip() if form.date_range.data else None
        series.notes = form.notes.data.strip() if form.notes.data else None

        try:
            db.session.commit()
            flash('Series updated successfully.', 'success')
            return redirect(url_for('admin.series_index'))
        except IntegrityError:
            db.session.rollback()
            flash('Another series already uses that name and volume.', 'warning')

    return render_template('admin/edit_series.html', form=form, series=series)


@admin_bp.route('/series/<int:series_id>/import-comicvine', methods=['POST'])
@admin_required
def import_comicvine_series(series_id):
    """Import issue metadata from a ComicVine volume into the Series Catalog."""
    series = Series.query.get_or_404(series_id)
    api_key = current_app.config.get('COMICVINE_API_KEY', '')
    if not api_key:
        flash('ComicVine API key is not configured.', 'danger')
        return redirect(url_for('admin.series_issues', series_id=series_id))

    volume_ref = (request.form.get('comicvine_volume') or '').strip()
    volume_id = series.comicvine_volume_id
    if volume_ref:
        parsed = parse_comicvine_volume_id(volume_ref)
        if parsed:
            volume_id = parsed
        elif volume_ref.isdigit():
            volume_id = int(volume_ref)

    if not volume_id:
        flash('Enter a ComicVine volume ID or URL (e.g. 4050-2914).', 'warning')
        return redirect(url_for('admin.series_issues', series_id=series_id))

    series.comicvine_volume_id = volume_id
    vol_meta = fetch_volume_detail(volume_id, api_key)
    if vol_meta.get('publisher_name') and not series.publisher:
        series.publisher = vol_meta['publisher_name']
    if vol_meta.get('start_year') and not series.date_range:
        series.date_range = vol_meta['start_year']

    imported = updated = 0
    offset = 0
    total = None
    while True:
        issues, total = fetch_volume_issues_for_import(
            volume_id, api_key, offset=offset, limit=100,
        )
        if not issues:
            break
        for item in issues:
            issue_num = (item.get('issue_number') or '').strip()
            if not issue_num:
                continue
            cv_id = item.get('comicvine_id')
            existing = SeriesIssue.query.filter_by(
                series_id=series.id, issue_number=issue_num,
            ).first()
            if existing:
                if cv_id and not existing.comicvine_issue_id:
                    existing.comicvine_issue_id = cv_id
                    updated += 1
                if item.get('writer') and not existing.writer:
                    existing.writer = item.get('writer')
                if item.get('artist') and not existing.artist:
                    existing.artist = item.get('artist')
                if item.get('story_arc') and not existing.story_arc:
                    existing.story_arc = item.get('story_arc')
                if item.get('characters') and not existing.featured_characters:
                    existing.featured_characters = item.get('characters')
                continue
            db.session.add(SeriesIssue(
                series_id=series.id,
                issue_number=issue_num,
                title=item.get('issue_title') or item.get('title'),
                cover_date=item.get('cover_date') or item.get('release_date'),
                featured_characters=item.get('characters'),
                writer=item.get('writer'),
                artist=item.get('artist'),
                story_arc=item.get('story_arc'),
                comicvine_issue_id=cv_id,
            ))
            imported += 1
        offset += len(issues)
        if total is not None and offset >= total:
            break
        if len(issues) < 100:
            break

    db.session.commit()
    flash(
        f'ComicVine import complete: {imported} new issue(s), {updated} link(s) updated.',
        'success',
    )
    return redirect(url_for('admin.series_issues', series_id=series_id))


@admin_bp.route('/roles')
@admin_required
def manage_roles():
    """List users and their admin/active roles."""
    users = User.query.order_by(User.username.asc()).all()
    admin_count = User.query.filter_by(is_admin=True).count()
    return render_template(
        'admin/roles.html',
        users=users,
        admin_count=admin_count,
        csrf_token=generate_csrf(),
    )


@admin_bp.route('/roles/<int:user_id>/toggle-admin', methods=['POST'])
@admin_required
def toggle_user_admin(user_id):
    """Grant or revoke admin access for a user."""
    user = db.session.get(User, user_id)
    if user is None:
        flash('User not found.', 'danger')
        return redirect(url_for('admin.manage_roles'))

    if user.id == current_user.id and user.is_admin:
        flash('You cannot remove your own admin access.', 'warning')
        return redirect(url_for('admin.manage_roles'))

    if user.is_admin:
        other_admins = User.query.filter(
            User.is_admin.is_(True),
            User.id != user.id,
        ).count()
        if other_admins == 0:
            flash('Cannot remove admin from the last admin account.', 'warning')
            return redirect(url_for('admin.manage_roles'))
        user.is_admin = False
        flash(f'Admin access removed from {user.username}.', 'success')
    else:
        user.is_admin = True
        flash(f'Admin access granted to {user.username}.', 'success')

    db.session.commit()
    return redirect(url_for('admin.manage_roles'))


@admin_bp.route('/roles/<int:user_id>/toggle-active', methods=['POST'])
@admin_required
def toggle_user_active(user_id):
    """Activate or deactivate a user account."""
    user = db.session.get(User, user_id)
    if user is None:
        flash('User not found.', 'danger')
        return redirect(url_for('admin.manage_roles'))

    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'warning')
        return redirect(url_for('admin.manage_roles'))

    user.is_active = not bool(user.is_active)
    db.session.commit()
    state = 'activated' if user.is_active else 'deactivated'
    flash(f'Account {user.username} {state}.', 'success')
    return redirect(url_for('admin.manage_roles'))


@admin_bp.route('/roles/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def reset_user_password(user_id):
    """Set a new password for another user (or yourself) from Manage Roles."""
    user = db.session.get(User, user_id)
    if user is None:
        flash('User not found.', 'danger')
        return redirect(url_for('admin.manage_roles'))

    password = (request.form.get('password') or '').strip()
    confirm = (request.form.get('confirm_password') or '').strip()

    if len(password) < 6:
        flash('Password must be at least 6 characters.', 'danger')
        return redirect(url_for('admin.manage_roles'))
    if password != confirm:
        flash('Passwords do not match.', 'danger')
        return redirect(url_for('admin.manage_roles'))

    user.set_password(password)
    user.clear_reset_token()
    db.session.commit()
    flash(f'Password reset for {user.username}.', 'success')
    return redirect(url_for('admin.manage_roles'))

