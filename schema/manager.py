# schema/manager.py: Manages database schema metadata

import os
import json
from collections import defaultdict
from typing import Dict
import logging
import logging.config

class SchemaManager:
    """Manages database schema metadata."""
    
    def __init__(self, db_name: str):
        """Initialize with database name."""
        logging_config_path = f"app-config/{db_name}/logging_config.ini"
        if os.path.exists(logging_config_path):
            try:
                logging.config.fileConfig(logging_config_path, disable_existing_loggers=False)
            except Exception as e:
                print(f"Error loading logging config: {e}")
        
        self.logger = logging.getLogger("schema")
        self.db_name = db_name
        self.cache_dir = os.path.join("schema_cache", db_name)
        self.cache_file = os.path.join(self.cache_dir, "schema.json")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.logger.debug(f"Initialized SchemaManager for {db_name}")
    
    def needs_refresh(self, conn) -> bool:
        """Check if schema cache needs refresh."""
        if not os.path.exists(self.cache_file):
            self.logger.debug("Schema cache missing, needs refresh")
            return True
        
        cached_time = os.path.getmtime(self.cache_file)
        latest_change = self._get_latest_schema_change(conn)
        
        needs_refresh = latest_change > cached_time if latest_change else True
        self.logger.debug(f"Schema refresh needed: {needs_refresh}")
        return needs_refresh
    
    def _get_latest_schema_change(self, conn) -> float:
        """Get timestamp of latest schema change."""
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT MAX(STATS_DATE(object_id, stats_id)) as last_updated
                    FROM sys.stats
                    WHERE object_id IN (
                        SELECT object_id 
                        FROM sys.tables 
                        WHERE is_ms_shipped = 0
                    )
                """)
                result = cursor.fetchone()
                timestamp = result[0].timestamp() if result[0] else 0
                self.logger.debug(f"Latest schema change: {timestamp}")
                return timestamp
        except Exception as e:
            self.logger.error(f"Error checking schema change: {e}")
            return 0
    
    def build_data_dict(self, conn) -> Dict:
        """Build schema dictionary."""
        self.logger.debug("Building schema dictionary")
        schema_dict = self._initialize_schema_dict()
        
        try:
            with conn.cursor() as cursor:
                self._fetch_schemas(cursor, schema_dict)
                self._fetch_tables(cursor, schema_dict)
                self._fetch_columns(cursor, schema_dict)
                self._fetch_primary_keys(cursor, schema_dict)
                self._fetch_foreign_keys(cursor, schema_dict)
                
                self._save_to_cache(schema_dict)
                self.logger.info("Schema dictionary built")
                return schema_dict
        except Exception as e:
            self.logger.error(f"Error building schema dictionary: {e}")
            raise
    
    def _initialize_schema_dict(self) -> Dict:
        """Initialize schema dictionary structure."""
        return {
            "database": self.db_name,
            "schemas": {},
            "tables": defaultdict(dict),
            "columns": defaultdict(lambda: defaultdict(dict)),
            "relationships": []
        }
    
    def _fetch_schemas(self, cursor, schema_dict: Dict):
        """Fetch schema names."""
        cursor.execute("""
            SELECT name, schema_id
            FROM sys.schemas
            WHERE principal_id = 1
        """)
        for row in cursor.fetchall():
            schema_dict["schemas"][row.name] = {
                "id": row.schema_id,
                "tables": []
            }
        self.logger.debug(f"Fetched schemas: {list(schema_dict['schemas'].keys())}")
    
    def _fetch_tables(self, cursor, schema_dict: Dict):
        """Fetch table names."""
        cursor.execute("""
            SELECT t.name AS table_name, s.name AS schema_name, t.object_id
            FROM sys.tables t
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            WHERE t.is_ms_shipped = 0
        """)
        for row in cursor.fetchall():
            schema_dict["tables"][row.schema_name][row.table_name] = {
                "id": row.object_id,
                "columns": []
            }
            schema_dict["schemas"][row.schema_name]["tables"].append(row.table_name)
        self.logger.debug(f"Fetched tables for schemas: {list(schema_dict['tables'].keys())}")
    
    def _fetch_columns(self, cursor, schema_dict: Dict):
        """Fetch column details."""
        cursor.execute("""
            SELECT 
                s.name AS schema_name,
                t.name AS table_name,
                c.name AS column_name,
                c.column_id,
                ty.name AS type_name,
                c.max_length,
                c.precision,
                c.scale,
                c.is_nullable,
                c.is_identity,
                ep.value AS description
            FROM sys.columns c
            JOIN sys.tables t ON c.object_id = t.object_id
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            JOIN sys.types ty ON c.user_type_id = ty.user_type_id
            LEFT JOIN sys.extended_properties ep ON 
                ep.major_id = c.object_id AND 
                ep.minor_id = c.column_id AND
                ep.name = 'MS_Description'
            WHERE t.is_ms_shipped = 0
        """)
        for row in cursor.fetchall():
            col_info = {
                "id": row.column_id,
                "type": row.type_name,
                "max_length": row.max_length,
                "precision": row.precision,
                "scale": row.scale,
                "nullable": bool(row.is_nullable),
                "identity": bool(row.is_identity),
                "description": row.description
            }
            schema_dict["columns"][row.schema_name][row.table_name][row.column_name] = col_info
            schema_dict["tables"][row.schema_name][row.table_name]["columns"].append(row.column_name)
        self.logger.debug("Fetched columns")
    
    def _fetch_primary_keys(self, cursor, schema_dict: Dict):
        """Fetch primary keys."""
        cursor.execute("""
            SELECT 
                s.name AS schema_name,
                t.name AS table_name,
                c.name AS column_name
            FROM sys.key_constraints kc
            JOIN sys.tables t ON kc.parent_object_id = t.object_id
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            JOIN sys.index_columns ic ON 
                ic.object_id = kc.parent_object_id AND
                ic.index_id = kc.unique_index_id
            JOIN sys.columns c ON 
                ic.object_id = c.object_id AND
                ic.column_id = c.column_id
            WHERE kc.type = 'PK'
        """)
        for row in cursor.fetchall():
            if row.column_name in schema_dict["columns"][row.schema_name][row.table_name]:
                schema_dict["columns"][row.schema_name][row.table_name][row.column_name]["is_primary_key"] = True
        self.logger.debug("Fetched primary keys")
    
    def _fetch_foreign_keys(self, cursor, schema_dict: Dict):
        """Fetch foreign keys."""
        cursor.execute("""
            SELECT 
                fs.name AS from_schema,
                ft.name AS from_table,
                fc.name AS from_column,
                ts.name AS to_schema,
                tt.name AS to_table,
                tc.name AS to_column
            FROM sys.foreign_key_columns fkc
            JOIN sys.tables ft ON fkc.parent_object_id = ft.object_id
            JOIN sys.schemas fs ON ft.schema_id = fs.schema_id
            JOIN sys.columns fc ON 
                fkc.parent_object_id = fc.object_id AND
                fkc.parent_column_id = fc.column_id
            JOIN sys.tables tt ON fkc.referenced_object_id = tt.object_id
            JOIN sys.schemas ts ON tt.schema_id = ts.schema_id
            JOIN sys.columns tc ON 
                fkc.referenced_object_id = tc.object_id AND
                fkc.referenced_column_id = tc.column_id
        """)
        for row in cursor.fetchall():
            relationship = {
                "from": f"{row.from_schema}.{row.from_table}.{row.from_column}",
                "to": f"{row.to_schema}.{row.to_table}.{row.to_column}",
                "cross_schema": row.from_schema != row.to_schema
            }
            schema_dict["relationships"].append(relationship)
        self.logger.debug("Fetched foreign keys")
    
    def _save_to_cache(self, schema_dict: Dict):
        """Save schema to cache."""
        with open(self.cache_file, 'w') as f:
            json.dump(schema_dict, f, indent=2)
        self.logger.debug(f"Saved schema to {self.cache_file}")
    
    def load_from_cache(self) -> Dict:
        """Load schema from cache."""
        with open(self.cache_file) as f:
            schema_dict = json.load(f)
            schema_dict['database'] = self.db_name
            self.logger.debug(f"Loaded schema from {self.cache_file}")
            return schema_dict