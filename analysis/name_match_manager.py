# analysis/name_match_manager.py: Manages name matching for entities

import os
import json
import logging
import logging.config
from typing import List, Dict
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class NameMatchManager:
    """Manages name matching for database entities."""
    
    def __init__(self, db_name: str):
        """Initialize with database name."""
        logging_config_path = f"app-config/{db_name}/logging_config.ini"
        if os.path.exists(logging_config_path):
            try:
                logging.config.fileConfig(logging_config_path, disable_existing_loggers=False)
            except Exception as e:
                print(f"Error loading logging config: {e}")
        
        self.logger = logging.getLogger("name_match_manager")
        self.db_name = db_name
        self.default_path = os.path.join("app-config", db_name, "default_name_matches.json")
        self.dynamic_path = os.path.join("app-config", db_name, "dynamic_name_matches.json")
        self.global_config_path = "app-config/global_defaults.json"
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.default_matches = self._load_default()
        self.dynamic_matches = self._load_dynamic()
        self.config = self._load_global_config()
        self.similarity_threshold = self.config.get('similarity_threshold', 0.7)
        self.logger.debug(f"Initialized NameMatchManager for {db_name}")

    def _load_global_config(self) -> Dict:
        """Load global configuration."""
        try:
            if os.path.exists(self.global_config_path):
                with open(self.global_config_path, 'r') as f:
                    self.logger.debug(f"Loaded global config from {self.global_config_path}")
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading global config: {e}")
        return {"similarity_threshold": 0.7, "prompt_threshold": 0.56}

    def _load_default(self) -> Dict[str, List[str]]:
        """Load default name matches."""
        try:
            if os.path.exists(self.default_path):
                with open(self.default_path, 'r') as f:
                    self.logger.debug(f"Loaded default matches from {self.default_path}")
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading default name matches: {e}")
        return {}

    def _load_dynamic(self) -> Dict[str, List[str]]:
        """Load dynamic name matches."""
        try:
            if os.path.exists(self.dynamic_path):
                with open(self.dynamic_path, 'r') as f:
                    self.logger.debug(f"Loaded dynamic matches from {self.dynamic_path}")
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading dynamic name matches: {e}")
        return {}

    def _save_dynamic(self):
        """Save dynamic name matches."""
        os.makedirs(os.path.dirname(self.dynamic_path), exist_ok=True)
        try:
            with open(self.dynamic_path, 'w') as f:
                json.dump(self.dynamic_matches, f, indent=2)
            self.logger.debug(f"Saved dynamic matches to {self.dynamic_path}")
        except Exception as e:
            self.logger.error(f"Error saving dynamic name matches: {e}")

    def save_to_default(self):
        """Merge dynamic matches into default."""
        os.makedirs(os.path.dirname(self.default_path), exist_ok=True)
        try:
            for col, synonyms in self.dynamic_matches.items():
                if col not in self.default_matches:
                    self.default_matches[col] = []
                for syn in synonyms:
                    if syn not in self.default_matches[col]:
                        self.default_matches[col].append(syn)
            with open(self.default_path, 'w') as f:
                json.dump(self.default_matches, f, indent=2)
            self.logger.debug(f"Saved default matches to {self.default_path}")
        except Exception as e:
            self.logger.error(f"Error saving default name matches: {e}")

    def get_synonyms(self, column: str) -> List[str]:
        """Get synonyms for a column."""
        col_lower = column.lower()
        synonyms = self.dynamic_matches.get(col_lower, []) or self.default_matches.get(col_lower, [])
        self.logger.debug(f"Synonyms for '{col_lower}': {synonyms}")
        return [column] + synonyms

    def get_token_embeddings(self, tokens: List[str]) -> np.ndarray:
        """Generate embeddings for tokens."""
        try:
            embeddings = self.model.encode(tokens)
            self.logger.debug(f"Generated embeddings for {len(tokens)} tokens")
            return embeddings
        except Exception as e:
            self.logger.error(f"Error generating token embeddings: {e}")
            return np.array([])

    def get_column_score(self, column: str, token_embeddings: np.ndarray) -> float:
        """Calculate similarity score for column."""
        if not token_embeddings.size:
            return 0.0
        try:
            col_embedding = self.model.encode([column]).reshape(1, -1)
            similarities = cosine_similarity(col_embedding, token_embeddings)[0]
            score = max(similarities) if max(similarities) > self.similarity_threshold else 0.0
            self.logger.debug(f"Column score for '{column}': {score}")
            return score
        except Exception as e:
            self.logger.error(f"Error calculating column score: {e}")
            return 0.0

    def update_synonyms(self, tokens: List[str], token_embeddings: np.ndarray, columns: List[str]):
        """Update synonyms based on matches."""
        if not token_embeddings.size:
            self.logger.debug("No embeddings provided")
            return

        for col in columns:
            col_lower = col.lower()
            col_embedding = self.model.encode([col]).reshape(1, -1)
            similarities = cosine_similarity(col_embedding, token_embeddings)[0]
            
            for token, sim in zip(tokens, similarities):
                if sim > self.similarity_threshold:
                    self._add_synonym(token, col_lower, sim)
                elif sim > self.config.get('prompt_threshold', 0.56):
                    self._prompt_for_synonym(token, col)

    def _add_synonym(self, token: str, column: str, similarity: float):
        """Add synonym if no conflicts."""
        token_lower = token.lower()
        if self._has_conflict(token_lower, column):
            self.logger.debug(f"Synonym conflict for '{token_lower}' with '{column}'")
            return
        
        if column not in self.dynamic_matches:
            self.dynamic_matches[column] = []
        if token_lower not in self.dynamic_matches[column]:
            self.dynamic_matches[column].append(token_lower)
            self.logger.info(f"Added synonym '{token_lower}' for '{column}' (sim={similarity:.2f})")

    def _prompt_for_synonym(self, token: str, column: str):
        """Prompt user for synonym confirmation."""
        token_lower = token.lower()
        if self._has_conflict(token_lower, column):
            self.logger.debug(f"Synonym conflict for '{token_lower}' with '{column}'")
            return
        
        # Check existing synonyms
        for col, synonyms in self.dynamic_matches.items():
            if token_lower in synonyms and col == column.lower():
                self.logger.debug(f"Synonym '{token_lower}' already exists for '{column}'")
                return
        
        confirm = input(f"Does '{token}' refer to column '{column}'? (y/n): ").strip().lower()
        if confirm == 'y':
            if column not in self.dynamic_matches:
                self.dynamic_matches[column] = []
            if token_lower not in self.dynamic_matches[column]:
                self.dynamic_matches[column].append(token_lower)
                self.logger.info(f"User confirmed synonym '{token_lower}' for '{column}'")
                self._save_dynamic()

    def _has_conflict(self, token: str, column: str) -> bool:
        """Check for synonym conflicts."""
        for col, synonyms in self.dynamic_matches.items():
            if col != column and token in synonyms:
                return True
        for col, synonyms in self.default_matches.items():
            if col != column and token in synonyms:
                return True
        return False

    def get_unmatched_tokens(self, tokens: List[str], columns: List[str]) -> List[str]:
        """Return unmatched tokens."""
        matched = set()
        for col in columns:
            matched.update(self.get_synonyms(col))
        unmatched = [t for t in tokens if t.lower() not in matched]
        self.logger.debug(f"Unmatched tokens: {unmatched}")
        return unmatched

    def save_dynamic(self):
        """Save dynamic matches."""
        self._save_dynamic()