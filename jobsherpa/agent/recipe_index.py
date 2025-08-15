import os
import yaml
import logging
from typing import List, Optional, Dict, Any


logger = logging.getLogger(__name__)


class RecipeIndex:
    """
    Abstract interface for indexing and retrieving application recipes.
    """

    def index(self) -> None:
        raise NotImplementedError

    def find_best(self, prompt: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError


class SimpleKeywordIndex(RecipeIndex):
    """
    Simple in-process keyword matcher over recipe YAMLs in knowledge_base/applications.

    Scoring: counts how many declared keywords appear as substrings in the prompt (case-insensitive).
    Returns the highest-scoring recipe, or None if all scores are zero.
    """

    def __init__(self, knowledge_base_dir: str):
        self.knowledge_base_dir = knowledge_base_dir
        self._recipes: List[Dict[str, Any]] = []

    def index(self) -> None:
        app_dir = os.path.join(self.knowledge_base_dir, "applications")
        if not os.path.isdir(app_dir):
            logger.warning("Applications directory not found for indexing: %s", app_dir)
            self._recipes = []
            return

        recipes: List[Dict[str, Any]] = []
        for filename in os.listdir(app_dir):
            if filename.endswith(".yaml"):
                path = os.path.join(app_dir, filename)
                try:
                    with open(path, "r") as f:
                        recipe = yaml.safe_load(f)
                        if isinstance(recipe, dict):
                            recipes.append(recipe)
                except Exception as e:
                    logger.warning("Failed to load recipe %s: %s", path, e)
        self._recipes = recipes

    def find_best(self, prompt: str) -> Optional[Dict[str, Any]]:
        if not self._recipes:
            self.index()
        prompt_l = prompt.lower()
        best_score = 0
        best_recipe = None
        for recipe in self._recipes:
            keywords = [k.lower() for k in recipe.get("keywords", [])]
            score = sum(1 for k in keywords if k and k in prompt_l)
            if score > best_score:
                best_score = score
                best_recipe = recipe
        return best_recipe if best_score > 0 else None


