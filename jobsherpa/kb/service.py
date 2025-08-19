import os
import logging
from typing import Optional, Tuple

from jobsherpa.util.io import read_yaml
from jobsherpa.kb.models import SystemProfile, SchedulerProfile, SiteProfile

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
	"""Centralized access to knowledge base files with consistent logging."""

	def __init__(self, base_dir: str = "knowledge_base") -> None:
		self.base_dir = base_dir

	def load_system(self, name: str) -> Tuple[Optional[dict], Optional[SystemProfile]]:
		path = os.path.join(self.base_dir, "system", f"{name}.yaml")
		if not os.path.exists(path):
			return None, None
		logger.debug("KB_LOAD kind=system path=%s name=%s", path, name)
		data = read_yaml(path)
		model: Optional[SystemProfile] = None
		try:
			model = SystemProfile.model_validate(data)  # type: ignore[attr-defined]
		except AttributeError:
			try:
				model = SystemProfile.parse_obj(data)  # type: ignore[attr-defined]
			except Exception:
				model = None
		return data, model

	def load_scheduler_profile(self, name: str) -> Optional[SchedulerProfile]:
		path = os.path.join(self.base_dir, "schedulers", f"{name}.yaml")
		if not os.path.exists(path):
			return None
		logger.debug("KB_LOAD kind=scheduler path=%s name=%s", path, name)
		data = read_yaml(path)
		try:
			return SchedulerProfile.model_validate(data)  # type: ignore[attr-defined]
		except AttributeError:
			return SchedulerProfile.parse_obj(data)  # type: ignore[attr-defined]

	def load_site_profile(self, name: str) -> Optional[SiteProfile]:
		path = os.path.join(self.base_dir, "site", f"{name}.yaml")
		if not os.path.exists(path):
			return None
		logger.debug("KB_LOAD kind=site path=%s name=%s", path, name)
		data = read_yaml(path)
		try:
			return SiteProfile.model_validate(data)  # type: ignore[attr-defined]
		except AttributeError:
			return SiteProfile.parse_obj(data)  # type: ignore[attr-defined]

	def find_site_for_system(self, system_name: str) -> Optional[SiteProfile]:
		site_dir = os.path.join(self.base_dir, "site")
		if not os.path.isdir(site_dir):
			return None
		for fname in os.listdir(site_dir):
			if not fname.endswith(".yaml"):
				continue
			name = os.path.splitext(fname)[0]
			site = self.load_site_profile(name)
			if site and any(s.lower() == system_name.lower() for s in site.systems):
				return site
		return None


