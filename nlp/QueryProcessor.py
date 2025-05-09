# nlp/QueryProcessor.py: Processes natural language queries into SQL
# Basic version for TableIdentifier-Working-Version-1

import os
import logging
import logging.config
from typing import Dict, List, Tuple
from analysis.table_identifier import TableIdentifier
from analysis.name_match_manager import NameMatchManager
from analysis.processor import NLPPipeline
from config.patterns import PatternManager
from config.manager import DatabaseConnection

class QueryProcessor:
    """Processes natural language queries into SQL."""
    
    def __init__(
        self,
        connection_manager: DatabaseConnection,
        schema_dict: Dict,
        nlp_pipeline: NLPPipeline,
        table_identifier: TableIdentifier,
        name_matcher: NameMatchManager,
        pattern_manager: PatternManager,
        db_name: str
    ):
        """Initialize with required components."""
        logging_config_path = f"app-config/logging_config.ini"
        if os.path.exists(logging_config_path):
            try:
                logging.config.fileConfig(logging_config_path, disable_existing_loggers=False)
            except Exception as e:
                print(f"Error loading logging config: {e}")
        
        self.logger = logging.getLogger("query_processor")
        self.connection_manager = connection_manager
        self.schema_dict = schema_dict
        self.nlp_pipeline = nlp_pipeline
        self.table_identifier = table_identifier
        self.name_matcher = name_matcher
        self.pattern_manager = pattern_manager
        self.db_name = db_name
        self.logger.debug(f"Initialized QueryProcessor for {db_name}")

    def process_query(self, query: str) -> Tuple[List[str], bool]:
        """Process a natural language query."""
        self.logger.debug(f"Processing query: {query}")
        tables, confidence = self.table_identifier.identify_tables(query)
        if not tables:
            self.logger.warning("No tables identified")
            return None, False

        # Basic column matching
        analysis = self.nlp_pipeline.analyze_query(query)
        tokens = analysis["tokens"]
        for token in tokens:
            for table in tables:
                schema, tbl = table.split('.')
                columns = self.schema_dict['columns'][schema][tbl]
                self.name_matcher.update_synonyms([token], self.name_matcher.get_token_embeddings([token]), columns)

        self.table_identifier.update_weights_from_feedback(query, tables)
        self.logger.info(f"Identified tables: {tables}, Confidence: {confidence}")
        return tables, confidence