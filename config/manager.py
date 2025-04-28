# config/manager.py
import os
import json
import pyodbc
from typing import Dict, Optional

class DatabaseConnection:
    def __init__(self):
        self.connection = None
        self.current_config = None

    def connect(self, config: Dict) -> bool:
        try:
            conn_str = (
                f"DRIVER={{{config['driver']}}};"
                f"SERVER={config['server']};"
                f"DATABASE={config['database']};"
                f"UID={config['username']};"
                f"PWD={config['password']}"
            )
            self.connection = pyodbc.connect(conn_str)
            self.current_config = config
            return True
        except Exception as e:
            print(f"Connection failed: {str(e)}")
            return False

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None
            self.current_config = None

    def is_connected(self) -> bool:
        return self.connection is not None

    def get_cursor(self) -> Optional[pyodbc.Cursor]:
        return self.connection.cursor() if self.connection else None
class DBConfigManager:
    def load_configs(self, config_path: str) -> Dict:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found at {config_path}")
        
        with open(config_path) as f:
            configs = json.load(f)
        
        self._validate_configs(configs)
        return configs

    def _validate_configs(self, configs: Dict):
        if not isinstance(configs, dict):
            raise ValueError("Config file should contain a dictionary of configurations")
        
        required_keys = {'server', 'database', 'username', 'password', 'driver'}
        for key, config in configs.items():
            if not isinstance(config, dict):
                raise ValueError(f"Configuration for {key} must be a dictionary")
            if not required_keys.issubset(config.keys()):
                missing = required_keys - set(config.keys())
                raise ValueError(f"Missing keys in {key} config: {', '.join(missing)}")