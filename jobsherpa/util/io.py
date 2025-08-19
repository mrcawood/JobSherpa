import yaml
import logging

logger = logging.getLogger(__name__)


def read_yaml(path: str):
	"""Read a YAML file with a debug log of the access."""
	logger.debug("Reading YAML file: %s", path)
	with open(path, "r") as f:
		return yaml.safe_load(f) or {}


