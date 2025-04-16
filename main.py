# main.py: Entry point for Database Schema Analyzer
# Initializes components and runs CLI

import logging
import logging.config
import os
from typing import Dict, List, Tuple
from database.connection import DatabaseConnection
from config.manager import DBConfigManager
from config.patterns import PatternManager
from schema.manager import SchemaManager
from feedback.manager import FeedbackManager
from analysis.table_identifier import TableIdentifier
from analysis.name_match_manager import NameMatchManager
from analysis.processor import NLPPipeline
from nlp.QueryProcessor import QueryProcessor
from cli.interface import DatabaseAnalyzerCLI

class DatabaseAnalyzer:
    """Main class for database schema analysis and query processing."""
    
    def __init__(self):
        """Initialize logging and components."""
        logging_config_path = "app-config/BikeStores/logging_config.ini"
        if os.path.exists(logging_config_path):
            try:
                logging.config.fileConfig(logging_config_path, disable_existing_loggers=False)
            except Exception as e:
                print(f"Error loading logging config: {e}")
        
        self.logger = logging.getLogger("analyzer")
        self.connection_manager = DatabaseConnection()
        self.config_manager = DBConfigManager()
        self.schema_manager = None
        self.pattern_manager = None
        self.feedback_manager = None
        self.nlp_pipeline = None
        self.name_matcher = None
        self.table_identifier = None
        self.query_processor = None
        self.current_config = None
        self.schema_dict = {}
        self.logger.debug("Initialized DatabaseAnalyzer")

    def run(self):
        """Run the CLI."""
        cli = DatabaseAnalyzerCLI(self)
        cli.run()
        if self.table_identifier:
            self.table_identifier.save_name_matches()
        if self.connection_manager:
            self.connection_manager.close()
        self.logger.info("Application shutdown")

    def load_configs(self, config_path: str = "app-config/database_configurations.json") -> Dict:
        """Load database configurations."""
        if not os.path.exists(config_path):
            self.logger.warning(f"Config file not found at {config_path}")
            config_path = input("Enter config file path: ").strip()
        configs = self.config_manager.load_configs(config_path)
        self.logger.debug(f"Loaded {len(configs)} configurations")
        return configs

    def set_current_config(self, config: Dict):
        """Set the current database configuration."""
        self.current_config = config
        self.logger.debug(f"Set config: {config.get('database')}")

    def connect_to_database(self) -> bool:
        """Connect to the selected database."""
        if not self.current_config:
            self.logger.error("No configuration selected")
            return False
            
        if self.connection_manager.connect(self.current_config):
            try:
                self._initialize_managers()
                self.logger.info(f"Connected to {self.current_config['database']}")
                return True
            except Exception as e:
                self.logger.error(f"Initialization error: {e}")
                raise
        self.logger.error("Database connection failed")
        return False

    def _initialize_managers(self):
        """Initialize all component managers."""
        db_name = self.current_config['database']
        self.logger.debug(f"Initializing managers for {db_name}")
        self.schema_manager = SchemaManager(db_name)
        
        if self.schema_manager.needs_refresh(self.connection_manager.connection):
            self.logger.debug("Building fresh schema")
            self.schema_dict = self.schema_manager.build_data_dict(
                self.connection_manager.connection
            )
        else:
            self.logger.debug("Loading schema from cache")
            self.schema_dict = self.schema_manager.load_from_cache()
        
        self.pattern_manager = PatternManager(self.schema_dict)
        self.feedback_manager = FeedbackManager(db_name)
        self.nlp_pipeline = NLPPipeline(self.pattern_manager, db_name)
        self.name_matcher = NameMatchManager(db_name)
        self.table_identifier = TableIdentifier(
            self.schema_dict,
            self.feedback_manager,
            self.pattern_manager
        )
        self.query_processor = QueryProcessor(
            self.connection_manager,
            self.schema_dict,
            self.nlp_pipeline,
            self.table_identifier,
            self.name_matcher,
            self.pattern_manager,
            db_name
        )
        self.logger.debug("Managers initialized")

    def reload_all_configurations(self) -> bool:
        """Reload all configurations and caches."""
        if not self.connection_manager.is_connected():
            self.logger.error("Not connected to database")
            print("Not connected to database!")
            return False
            
        try:
            self.logger.debug("Rebuilding schema")
            self.schema_dict = self.schema_manager.build_data_dict(
                self.connection_manager.connection
            )
            self.pattern_manager = PatternManager(self.schema_dict)
            self.feedback_manager = FeedbackManager(self.current_config['database'])
            self.nlp_pipeline = NLPPipeline(self.pattern_manager, self.current_config['database'])
            self.name_matcher = NameMatchManager(self.current_config['database'])
            self.table_identifier = TableIdentifier(
                self.schema_dict,
                self.feedback_manager,
                self.pattern_manager
            )
            self.query_processor = QueryProcessor(
                self.connection_manager,
                self.schema_dict,
                self.nlp_pipeline,
                self.table_identifier,
                self.name_matcher,
                self.pattern_manager,
                self.current_config['database']
            )
            self.logger.info("Configurations reloaded")
            return True
        except Exception as e:
            self.logger.error(f"Reload failed: {e}")
            print(f"Reload failed: {e}")
            return False

    def process_query(self, query: str) -> Tuple[List[str], bool]:
        """Process a natural language query."""
        if not self.connection_manager.is_connected():
            self.logger.error("Not connected to database")
            print("Not connected to database!")
            return None, False
            
        if self.query_processor is None:
            self.logger.error("Query processor not initialized")
            print("Query processor not initialized. Please connect to the database.")
            return None, False
            
        try:
            tables, confidence = self.query_processor.process_query(query)
            self.logger.debug(f"Query: {query}, Tables: {tables}, Confidence: {confidence}")
            return tables, confidence
        except Exception as e:
            self.logger.error(f"Query processing error: {e}")
            print(f"Query processing error: {e}")
            return None, False

    def validate_tables_exist(self, tables: List[str]) -> Tuple[List[str], List[str]]:
        """Validate tables against current schema."""
        valid = []
        invalid = []
        schema_map = {s.lower(): s for s in self.schema_dict['tables']}
        
        for table in tables:
            parts = table.split('.')
            if len(parts) != 2:
                invalid.append(table)
                continue
                
            schema, table_name = parts
            schema_lower = schema.lower()
            
            if (schema_lower in schema_map and 
                table_name.lower() in {t.lower() for t in self.schema_dict['tables'][schema_map[schema_lower]]}):
                valid.append(f"{schema_map[schema_lower]}.{table_name}")
            else:
                invalid.append(table)
                
        self.logger.debug(f"Validated tables: Valid={valid}, Invalid={invalid}")
        return valid, invalid

    def generate_ddl(self, tables: List[str]):
        """Generate DDL for specified tables."""
        for table in tables:
            if '.' not in table:
                print(f"Invalid format: {table}")
                continue
                
            schema, table_name = table.split('.')
            if schema not in self.schema_dict['tables']:
                print(f"Schema not found: {schema}")
                continue
                
            if table_name not in self.schema_dict['tables'][schema]:
                print(f"Table not found: {table_name} in schema {schema}")
                continue
                
            self.logger.debug(f"Generating DDL for {schema}.{table_name}")
            print(f"\n-- DDL for {schema}.{table_name}")
            columns = self.schema_dict['columns'][schema][table_name]
            col_defs = []
            
            for col_name, col_info in columns.items():
                col_def = f"    [{col_name}] {col_info['type']}"
                if col_info.get('is_primary_key'):
                    col_def += " PRIMARY KEY"
                if not col_info.get('nullable'):
                    col_def += " NOT NULL"
                col_defs.append(col_def)
                
            print("CREATE TABLE [{}].[{}] (\n{}\n);".format(
                schema, table_name, ",\n".join(col_defs)
            ))

    def close_connection(self):
        """Close database connection."""
        self.connection_manager.close()
        self.logger.info("Database connection closed")

    def is_connected(self) -> bool:
        """Check connection status."""
        return self.connection_manager.is_connected()

    def get_all_tables(self) -> List[str]:
        """Get list of all tables in schema."""
        tables = []
        for schema in self.schema_dict['tables']:
            tables.extend(f"{schema}.{table}" for table in self.schema_dict['tables'][schema])
        self.logger.debug(f"All tables: {tables}")
        return tables

    def confirm_tables(self, query: str, tables: List[str]):
        """Confirm correct tables for a query."""
        if self.feedback_manager:
            self.feedback_manager.store_feedback(query, tables, self.schema_dict)
            if self.table_identifier:
                self.table_identifier.update_weights_from_feedback(query, tables)
            self.logger.info(f"Confirmed tables for query: {query}")

    def update_feedback(self, query: str, tables: List[str]):
        """Update feedback with corrected tables."""
        if self.feedback_manager:
            self.feedback_manager.store_feedback(query, tables, self.schema_dict)
            if self.table_identifier:
                self.table_identifier.update_weights_from_feedback(query, tables)
            self.logger.info(f"Updated feedback for query: {query}")

    def clear_feedback(self):
        """Clear all feedback data."""
        if self.feedback_manager:
            self.feedback_manager.clear_feedback()
            print("Feedback cleared")
            self.logger.info("Feedback cleared")
        else:
            self.logger.error("Feedback manager not initialized")
            print("Feedback manager not initialized. Please connect to a database.")

if __name__ == "__main__":
    analyzer = DatabaseAnalyzer()
    analyzer.run()