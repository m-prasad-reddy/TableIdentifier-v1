# config/patterns.py: Manages patterns for query parsing

import json
import os
import re
from typing import Dict
import logging
import logging.config

class PatternManager:
    """Manages patterns for query analysis."""
    
    def __init__(self, schema_dict: Dict):
        """Initialize with schema dictionary."""
        logging_config_path = "app-config/logging_config.ini"
        if os.path.exists(logging_config_path):
            try:
                logging.config.fileConfig(logging_config_path, disable_existing_loggers=False)
            except Exception as e:
                print(f"Error loading logging config: {e}")
        
        self.logger = logging.getLogger("patterns")
        self.schema_dict = schema_dict
        self.pattern_weights = self._load_patterns()
        self.logger.debug(f"Initialized PatternManager with {len(self.pattern_weights)} patterns")

    def _load_patterns(self) -> Dict[str, Dict[str, float]]:
        """Load patterns from global_patterns.json."""
        pattern_path = "app-config/global_patterns.json"
        patterns = {}
        try:
            if os.path.exists(pattern_path):
                with open(pattern_path, 'r') as f:
                    patterns = json.load(f)
                self.logger.debug(f"Loaded patterns from {pattern_path}")
            else:
                self.logger.warning(f"Pattern file not found at {pattern_path}")
        except Exception as e:
            self.logger.error(f"Error loading patterns: {e}")
        
        # Normalize patterns
        normalized = {}
        for query, weights in patterns.items():
            norm_query = re.sub(r'\s+', ' ', query.lower().strip())
            normalized[norm_query] = {
                table: float(weight) for table, weight in weights.items()
            }
        return normalized

    def get_patterns(self) -> Dict[str, Dict[str, float]]:
        """Return the loaded patterns."""
        return self.pattern_weights