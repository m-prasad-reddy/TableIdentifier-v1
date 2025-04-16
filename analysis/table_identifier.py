# analysis/table_identifier.py: Identifies tables in queries
# Uses sentence_transformers and NameMatchManager

import spacy
from typing import Dict, List, Optional, Tuple
import json
import os
import logging
import logging.config
from sentence_transformers import SentenceTransformer
from analysis.name_match_manager import NameMatchManager

nlp = spacy.load("en_core_web_sm")

class TableIdentifier:
    """Identifies tables in natural language queries."""
    
    def __init__(self, schema_dict: Dict, feedback_manager, pattern_manager):
        """Initialize with schema, feedback, and patterns."""
        logging_config_path = "app-config/BikeStores/logging_config.ini"
        if os.path.exists(logging_config_path):
            try:
                logging.config.fileConfig(logging_config_path, disable_existing_loggers=False)
            except Exception as e:
                print(f"Error loading logging config: {e}")
        
        self.logger = logging.getLogger("table_identifier")
        self.schema_dict = schema_dict
        self.feedback_manager = feedback_manager
        self.pattern_manager = pattern_manager
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.name_match_manager = NameMatchManager(feedback_manager.db_name)
        self.weights = self._load_weights()
        self.logger.debug("Initialized TableIdentifier")

    def _load_weights(self) -> Dict:
        """Load table weights."""
        weights_path = os.path.join("schema_cache", self.feedback_manager.db_name, "weights.json")
        if os.path.exists(weights_path):
            try:
                with open(weights_path) as f:
                    self.logger.debug(f"Loaded weights from {weights_path}")
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Error loading weights: {e}")
        return {}

    def _save_weights(self):
        """Save table weights."""
        weights_path = os.path.join("schema_cache", self.feedback_manager.db_name, "weights.json")
        os.makedirs(os.path.dirname(weights_path), exist_ok=True)
        try:
            with open(weights_path, 'w') as f:
                json.dump(self.weights, f)
            self.logger.debug(f"Saved weights to {weights_path}")
        except Exception as e:
            self.logger.error(f"Error saving weights: {e}")

    def save_name_matches(self):
        """Save dynamic name matches."""
        self.name_match_manager.save_to_default()
        self.logger.debug("Saved name matches")

    def identify_tables(self, query: str) -> Tuple[Optional[List[str]], bool]:
        """Identify tables in query."""
        self.logger.debug(f"Identifying tables for query: {query}")
        feedback = self.feedback_manager.get_similar_feedback(query)
        if feedback and feedback[0]['tables']:
            tables = feedback[0]['tables']
            valid_tables, _ = self.feedback_manager.validate_tables(tables, self.schema_dict)
            if valid_tables:
                self.logger.info(f"Used feedback tables: {valid_tables}")
                return valid_tables, True
        return self._identify_tables_nlp(query)

    def _identify_tables_nlp(self, query: str) -> Tuple[Optional[List[str]], bool]:
        """Identify tables using NLP."""
        try:
            doc = nlp(query.lower())
            table_scores = {}
            token_embeddings = self.name_match_manager.get_token_embeddings([t.lemma_ for t in doc])
            
            for schema in self.schema_dict['tables']:
                for table in self.schema_dict['tables'][schema]:
                    table_full = f"{schema}.{table}"
                    score = 0.0
                    
                    if table.lower() in query.lower():
                        score += 0.5
                    
                    for col in self.schema_dict['columns'][schema][table]:
                        col_score = self.name_match_manager.get_column_score(col, token_embeddings)
                        score += col_score * 0.8
                    
                    score += self.pattern_manager.get_pattern_weight(query, table_full)
                    for token in doc:
                        lemma = token.lemma_.lower()
                        score += self.weights.get(table_full, {}).get(lemma, 0.0)
                    
                    if score > 0:
                        table_scores[table_full] = score
            
            sorted_tables = sorted(table_scores.items(), key=lambda x: x[1], reverse=True)[:5]
            selected_tables = [table for table, _ in sorted_tables]
            
            confidence = bool(selected_tables)
            self.logger.debug(f"Tables: {selected_tables}, Confidence: {confidence}")
            return selected_tables or None, confidence
        
        except Exception as e:
            self.logger.error(f"NLP error: {e}")
            return None, False

    def update_weights_from_feedback(self, query: str, tables: List[str]):
        """Update weights based on feedback."""
        self.logger.debug(f"Updating weights for query: {query}, Tables: {tables}")
        doc = nlp(query.lower())
        tokens = [token.lemma_.lower() for token in doc if token.pos_ in ('NOUN', 'VERB', 'ADJ')]
        
        for table in tables:
            schema, table_name = table.split('.')
            columns = self.schema_dict['columns'][schema][table_name]
            token_embeddings = self.name_match_manager.get_token_embeddings(tokens)
            self.name_match_manager.update_synonyms(tokens, token_embeddings, columns)
            
            unmatched = self.name_match_manager.get_unmatched_tokens(tokens, columns)
            table_weights = self.weights.get(table, {})
            for token in unmatched:
                table_weights[token] = table_weights.get(token, 0.0) + 0.1
            self.weights[table] = table_weights
        
        self._save_weights()
        self.name_match_manager.save_dynamic()
        self.logger.debug("Weights updated")