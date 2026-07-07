from flask import Blueprint

onboarding_bp = Blueprint(
    "onboarding",
    __name__,
    url_prefix="/onboarding",
    template_folder="../templates/onboarding",
)

from . import routes  # noqa: E402,F401  (registers routes on import)
