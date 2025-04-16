import os
from typing import Dict, List
import spacy
import shutil
import json

class DatabaseAnalyzerCLI:
    def __init__(self, analyzer):
        self.analyzer = analyzer
        self.nlp = spacy.load("en_core_web_sm")

    def run(self):
        db_name = self.analyzer.current_config.get('database', 'Database') if self.analyzer.current_config else 'Database'
        print(f"=== {db_name} Schema Analyzer ===")
        while True:
            print("\nMain Menu:")
            print("1. Connect to Database")
            print("2. Query Mode")
            print("3. Reload Configurations")
            print("4. Manage Feedback")
            print("5. Exit")
            
            choice = input("Select option: ").strip()
            
            if choice == "1":
                self._handle_connection()
                # Update title after connection
                db_name = self.analyzer.current_config.get('database', 'Database') if self.analyzer.current_config else 'Database'
                print(f"\n=== {db_name} Schema Analyzer ===")
            elif choice == "2":
                self._query_mode()
            elif choice == "3":
                self._reload_configurations()
            elif choice == "4":
                self._manage_feedback()
            elif choice == "5":
                print("Exiting...")
                break
            else:
                print("Invalid choice")

    def _handle_connection(self):
        config_path = input("Config path [default: app-config/database_configurations.json]: ").strip()
        if not config_path:
            config_path = "app-config/database_configurations.json"
        
        try:
            configs = self.analyzer.load_configs(config_path)
            self._select_configuration(configs)
            if self.analyzer.connect_to_database():
                print("Successfully connected!")
            else:
                print("Connection failed: Unable to establish database connection")
        except Exception as e:
            print(f"Connection failed: {str(e)}")

    def _select_configuration(self, configs: Dict):
        print("\nAvailable Configurations:")
        for i, name in enumerate(configs.keys(), 1):
            print(f"{i}. {name}")
        print(f"{len(configs)+1}. Cancel")
        
        while True:
            choice = input("Select configuration: ").strip()
            if choice.isdigit():
                index = int(choice) - 1
                if 0 <= index < len(configs):
                    config = list(configs.values())[index]
                    self.analyzer.set_current_config(config)
                    return
                elif index == len(configs):
                    return
            print("Invalid selection")

    def _validate_query(self, query: str) -> bool:
        """Validate if the query is meaningful"""
        if not query or query.isspace():
            return False
            
        # Check for single word or number
        tokens = query.strip().split()
        if len(tokens) <= 1:
            return False
        if query.strip().isdigit():
            return False
            
        # Use spaCy to check for meaningful content
        doc = self.nlp(query.lower())
        has_noun_chunk = any(chunk for chunk in doc.noun_chunks)
        has_verb = any(token.pos_ == "VERB" for token in doc)
        
        # Reject meaningless phrases (e.g., repetitive words, gibberish)
        if not (has_noun_chunk or has_verb):
            return False
            
        # Reject short, vague phrases
        if len(doc) < 3 and not has_noun_chunk:
            return False
            
        return True

    def _query_mode(self):
        if not self.analyzer.is_connected():
            print("Not connected to database!")
            return
            
        # Display example queries
        try:
            example_queries = self.analyzer.feedback_manager.get_top_queries(3)
            if example_queries:
                print("\nExample Queries:")
                for i, (query, count) in enumerate(example_queries, 1):
                    print(f"{i}. {query} (used {count} times)")
            else:
                print("\nNo example queries available. Try these formats:")
                print("1. Show me all stores with store names")
                print("2. List all products with prices")
                print("3. Show customers from a specific city")
        except Exception as e:
            print(f"Error loading example queries: {str(e)}")
            
        while True:
            query = input("\nEnter query (or 'back'): ").strip()
            if query.lower() == 'back':
                return
                
            if not self._validate_query(query):
                print("Please enter a meaningful query (e.g., 'show me all stores with store names').")
                print("Avoid single words, numbers, or vague phrases.")
                continue
                
            results, confidence = self.analyzer.process_query(query)
            if results is None:
                print("Unable to process query. Please try again or reconnect.")
                continue
                
            if confidence and results:
                print("\nSuggested Tables:")
                for i, table in enumerate(results[:5], 1):  # Limit to top 5
                    print(f"{i}. {table}")
                self._handle_feedback(query, results)
            else:
                print("\nLow confidence. Please select tables manually:")
                self._manual_table_selection(query)

    def _handle_feedback(self, query: str, results: List[str]):
        while True:
            feedback = input("\nCorrect? (Y/N): ").strip().lower()
            if feedback in ('y', 'n'):
                break
            print("Please enter 'Y' or 'N'.")
        
        if feedback == 'y':
            self.analyzer.confirm_tables(query, results)
        elif feedback == 'n':
            correct_tables = self._get_manual_tables()
            if correct_tables:
                self.analyzer.update_feedback(query, correct_tables)

    def _get_manual_tables(self) -> List[str]:
        print("Available Tables:")
        tables = self.analyzer.get_all_tables()
        for i, table in enumerate(tables, 1):
            print(f"{i}. {table}")
            
        selection = input("Enter table numbers or names (comma-separated, e.g., '6' or 'sales.stores'): ").strip()
        if not selection:
            return []
            
        selected = []
        items = [s.strip() for s in selection.split(',')]
        
        for item in items:
            # Try as index
            if item.isdigit():
                try:
                    index = int(item) - 1
                    if 0 <= index < len(tables):
                        selected.append(tables[index])
                except (IndexError, ValueError):
                    continue
            # Try as table name
            elif '.' in item:
                schema, table_name = item.split('.', 1)
                if any(t.lower() == item.lower() for t in tables):
                    selected.append(item)
        
        if not selected:
            print("Invalid selection, please try again")
        return selected

    def _manual_table_selection(self, query: str):
        selected_tables = self._get_manual_tables()
        if selected_tables:
            self.analyzer.update_feedback(query, selected_tables)

    def _reload_configurations(self):
        try:
            if self.analyzer.reload_all_configurations():
                print("Successfully reloaded configurations")
            else:
                print("Reload failed: Unable to reload configurations")
        except Exception as e:
            print(f"Reload failed: {str(e)}")

    def _manage_feedback(self):
        if not self.analyzer.is_connected():
            print("Please connect to a database to manage feedback.")
            return
            
        print("\nFeedback Management:")
        print("1. Export feedback")
        print("2. Import feedback")
        print("3. Clear local feedback")
        choice = input("Select option: ").strip()
        
        if choice == "1":
            self._export_feedback()
        elif choice == "2":
            self._import_feedback()
        elif choice == "3":
            try:
                self.analyzer.clear_feedback()
            except Exception as e:
                print(f"Error clearing feedback: {str(e)}")
        else:
            print("Invalid choice")

    def _export_feedback(self):
        if not self.analyzer.feedback_manager:
            print("Feedback manager not initialized. Please connect to a database.")
            return
            
        export_dir = input("Enter export directory path [default: feedback_cache/export]: ").strip()
        if not export_dir:
            export_dir = os.path.join("feedback_cache", "export")
            
        try:
            os.makedirs(export_dir, exist_ok=True)
            feedback_dir = self.analyzer.feedback_manager.feedback_dir
            copied = False
            for fname in os.listdir(feedback_dir):
                if fname.endswith("_meta.json"):
                    # Validate meta file
                    src = os.path.join(feedback_dir, fname)
                    with open(src) as f:
                        meta = json.load(f)
                    if 'query' not in meta or 'tables' not in meta or 'timestamp' not in meta:
                        print(f"Skipping invalid feedback file: {fname}")
                        continue
                    # Copy meta and corresponding emb file
                    dst = os.path.join(export_dir, fname)
                    shutil.copy2(src, dst)
                    emb_fname = fname.replace("_meta.json", "_emb.npy")
                    emb_src = os.path.join(feedback_dir, emb_fname)
                    if os.path.exists(emb_src):
                        shutil.copy2(emb_src, os.path.join(export_dir, emb_fname))
                    copied = True
            if copied:
                print(f"Feedback exported to {export_dir}")
            else:
                print("No valid feedback files to export")
        except Exception as e:
            print(f"Error exporting feedback: {str(e)}")

    def _import_feedback(self):
        if not self.analyzer.feedback_manager:
            print("Feedback manager not initialized. Please connect to a database.")
            return
            
        import_dir = input("Enter import directory path: ").strip()
        if not import_dir or not os.path.exists(import_dir):
            print("Invalid or non-existent directory")
            return
            
        try:
            feedback_dir = self.analyzer.feedback_manager.feedback_dir
            os.makedirs(feedback_dir, exist_ok=True)
            copied = False
            for fname in os.listdir(import_dir):
                if fname.endswith("_meta.json"):
                    # Validate meta file
                    src = os.path.join(import_dir, fname)
                    with open(src) as f:
                        meta = json.load(f)
                    if 'query' not in meta or 'tables' not in meta or 'timestamp' not in meta:
                        print(f"Skipping invalid feedback file: {fname}")
                        continue
                    # Copy meta and corresponding emb file
                    dst = os.path.join(feedback_dir, fname)
                    shutil.copy2(src, dst)
                    emb_fname = fname.replace("_meta.json", "_emb.npy")
                    emb_src = os.path.join(import_dir, emb_fname)
                    if os.path.exists(emb_src):
                        shutil.copy2(emb_src, os.path.join(feedback_dir, emb_fname))
                    copied = True
            if copied:
                self.analyzer.feedback_manager._load_feedback_cache()
                print(f"Feedback imported from {import_dir}")
            else:
                print("No valid feedback files to import")
        except Exception as e:
            print(f"Error importing feedback: {str(e)}")