import logging
from typing import Tuple

import jinja2

logger = logging.getLogger(__name__)


class ExceptionManager:
	"""
	Centralized exception-to-user-message mapping and logging policy.
	Keep user-facing messages concise; keep details in logs.
	"""

	@staticmethod
	def map_exception(exc: Exception) -> Tuple[str, int]:
		"""Return (user_message, log_level) for a given exception."""
		# Known classes
		if isinstance(exc, jinja2.TemplateNotFound):
			return (f"Template not found: {exc}.", logging.ERROR)
		# Pydantic present across versions
		if exc.__class__.__name__ in {"ValidationError"}:
			return ("Invalid configuration detected. Please fix your profile (workspace/system) or re-run with --debug for details.", logging.WARNING)
		if isinstance(exc, FileNotFoundError):
			return ("A required file was not found. Re-run with --debug for the missing path.", logging.ERROR)
		# Default fallback
		return ("An unexpected error occurred. Re-run with --debug for details.", logging.ERROR)

	@staticmethod
	def handle(exc: Exception) -> str:
		msg, level = ExceptionManager.map_exception(exc)
		logger.log(level, "Handled exception: %s", exc, exc_info=True)
		return msg


