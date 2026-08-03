"""Comics blueprint package.

Route modules register endpoints on comics_bp when imported below.
"""

from flask import Blueprint

comics_bp = Blueprint('comics', __name__)

from . import routes_barcode  # noqa: E402,F401
from . import routes_bulk  # noqa: E402,F401
from . import routes_covers  # noqa: E402,F401
from . import routes_crud  # noqa: E402,F401
from . import routes_export  # noqa: E402,F401
from . import routes_import  # noqa: E402,F401
from . import routes_search  # noqa: E402,F401
