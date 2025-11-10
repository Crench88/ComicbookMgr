"""
Administrative routes for managing comic metadata such as canonical series lists.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from flask_wtf.csrf import generate_csrf
import csv
from io import StringIO

from . import db
from .forms import SeriesForm, SeriesIssueForm, SeriesIssueUploadForm
from .models import Series, SeriesIssue, Comic

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/series', methods=['GET', 'POST'])
@login_required
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
@login_required
def delete_series(series_id):
    """Remove a series entry."""
    series = Series.query.get_or_404(series_id)
    db.session.delete(series)
    db.session.commit()
    flash('Series removed from your list.', 'success')
    return redirect(url_for('admin.series_index'))


@admin_bp.route('/series/issues', methods=['GET', 'POST'])
@login_required
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
        series = Series.query.get(selected_series_id)
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
@login_required
def delete_series_issue(issue_id):
    """Delete a canonical issue record."""
    issue = SeriesIssue.query.get_or_404(issue_id)
    series_id = issue.series_id
    db.session.delete(issue)
    db.session.commit()
    flash('Issue removed from the series list.', 'success')
    return redirect(url_for('admin.series_issues', series_id=series_id))


@admin_bp.route('/series/<int:series_id>/edit', methods=['GET', 'POST'])
@login_required
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

