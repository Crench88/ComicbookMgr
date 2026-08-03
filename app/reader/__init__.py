"""Digital comic reader blueprint."""

from flask import Blueprint

reader_bp = Blueprint('reader', __name__, url_prefix='/reader')

from . import routes  # noqa: E402,F401
