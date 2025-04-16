# TableIdentifier-v1
 Identify the table names from the given text query for selected database


## Components

Below is a detailed overview of each component in **TableIdentifier-Working-Version-1**, including purpose, functionality, and interactions.

### 1. main.py (DatabaseAnalyzer)
- **Purpose**: Serves as the entry point, orchestrating component initialization and user interaction via a command-line interface (CLI).
- **Functionality**:
  - Initializes logging using `app-config/BikeStores/logging_config.ini`.
  - Manages database connections (e.g., "BIKES_DB") via `DatabaseConnection`.
  - Coordinates component setup: `SchemaManager`, `PatternManager`, `FeedbackManager`, `NLPPipeline`, `NameMatchManager`, `TableIdentifier`, `QueryProcessor`.
  - Runs the CLI for database selection, query processing, configuration reloading, feedback management, and DDL generation.
  - Processes queries by delegating to `QueryProcessor` and confirming results via `FeedbackManager`.
- **Key Interactions**:
  - Loads configurations with `DBConfigManager.load_configs`.
  - Connects to databases using `DatabaseConnection.connect`.
  - Initializes components in `_initialize_managers`.
  - Processes queries via `QueryProcessor.process_query`.
  - Stores feedback with `FeedbackManager.store_feedback`.
- **Files**:
  - `main.py`

### 2. analysis/processor.py (NLPPipeline)
- **Purpose**: Analyzes natural language queries using spaCy for tokenization, entity recognition, and pattern matching.
- **Functionality**:
  - Loads the spaCy model `en_core_web_trf`.
  - Converts query patterns from `PatternManager` into spaCy matcher patterns.
  - Analyzes queries to extract tokens, entities, pattern matches, and dependencies.
  - Fixed spaCy `E178` error by generating patterns from query strings.
- **Key Interactions**:
  - Retrieves patterns via `PatternManager.get_patterns`.
  - Provides token analysis to `QueryProcessor` for synonym matching.
  - Logs analysis steps to `logs/bikestores_app.log`.
- **Files**:
  - `analysis/processor.py`

### 3. nlp/QueryProcessor.py (QueryProcessor)
- **Purpose**: Core component for mapping natural language queries to database tables and columns.
- **Functionality**:
  - Identifies relevant tables using `TableIdentifier`.
  - Analyzes queries with `NLPPipeline` to extract tokens.
  - Matches tokens to columns via `NameMatchManager` for synonym learning.
  - Updates feedback weights through `TableIdentifier`.
  - Currently returns table suggestions and confidence scores (basic version).
- **Key Interactions**:
  - Calls `TableIdentifier.identify_tables` for table detection.
  - Uses `NLPPipeline.analyze_query` for token extraction.
  - Updates synonyms with `NameMatchManager.update_synonyms`.
  - Logs query processing details.
- **Files**:
  - `nlp/QueryProcessor.py`

### 4. analysis/name_match_manager.py (NameMatchManager)
- **Purpose**: Manages synonym mappings for database columns using semantic similarity.
- **Functionality**:
  - Loads default (`default_name_matches.json`) and dynamic (`dynamic_name_matches.json`) synonym mappings.
  - Uses SentenceTransformer (`all-MiniLM-L6-v2`) to compute token-column similarities.
  - Prompts users to confirm synonyms (e.g., "Does 'availability' refer to 'quantity'?").
  - Saves new synonyms to `dynamic_name_matches.json`.
  - Fixed missing `os` import for file operations.
- **Key Interactions**:
  - Used by `QueryProcessor` and `TableIdentifier` for column matching.
  - Reads/writes JSON files in `app-config/BikeStores/`.
  - Logs synonym updates and prompts.
- **Files**:
  - `analysis/name_match_manager.py`
  - `app-config/BikeStores/default_name_matches.json`
  - `app-config/BikeStores/dynamic_name_matches.json`
  - `app-config/global_defaults.json`

### 5. config/patterns.py (PatternManager)
- **Purpose**: Manages query-to-table patterns for matching natural language queries.
- **Functionality**:
  - Loads patterns from `app-config/global_patterns.json`.
  - Normalizes query strings (lowercase, removes extra spaces).
  - Provides patterns to `NLPPipeline` for spaCy matching and `TableIdentifier` for table detection.
  - Added `get_patterns` method to fix `AttributeError` in `NLPPipeline`.
- **Key Interactions**:
  - Supplies patterns to `NLPPipeline._load_patterns`.
  - Supports `TableIdentifier.identify_tables` for pattern-based matching.
  - Logs pattern loading status.
- **Files**:
  - `config/patterns.py`
  - `app-config/global_patterns.json`

### 6. feedback/manager.py (FeedbackManager)
- **Purpose**: Stores and retrieves feedback for query-table mappings to improve table identification.
- **Functionality**:
  - Caches feedback in `feedback_cache/BikeStores/` (e.g., `20250416133007_meta.json`).
  - Extracts