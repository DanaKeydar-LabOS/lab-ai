import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
from models import SchemaIngestionStatus

logger = logging.getLogger(__name__)


class SchemaProcessor:
    """Process database schema files and prepare them for vector storage"""

    def __init__(self, kb_path: str, poc_tables: List[str]):
        self.kb_path = Path(kb_path)
        self.poc_tables = poc_tables

    async def ingest_schema(self, vector_store, sql_generator) -> SchemaIngestionStatus:
        """Ingest database schema into vector store"""
        try:
            logger.info("Starting enhanced schema ingestion with query examples...")

            # Reset vector store collection
            await vector_store.create_collection()

            if not self.kb_path.exists():
                raise FileNotFoundError(f"Knowledge base directory not found: {self.kb_path}")

            # Load catalog index
            catalog_data = await self._load_catalog_index()
            logger.info(f"Loaded catalog with {len(catalog_data)} tables")

            # Process POC tables
            processed_tables = 0
            schema_points = []

            for table_name in self.poc_tables:
                table_file = self.kb_path / f"{table_name}.json"

                if table_file.exists():
                    logger.info(f"Processing table: {table_name}")

                    # Load table data
                    table_data = self._load_table_file(table_file)
                    if not table_data:
                        logger.warning(f"Failed to load table data for {table_name}")
                        continue

                    # Get catalog info
                    catalog_info = catalog_data.get(table_name, {})

                    # Process schema into searchable text (now includes examples)
                    schema_text = self._process_table_schema_with_examples(table_data, table_name, catalog_info)

                    # Generate embedding
                    embedding = await sql_generator.get_embedding(schema_text)

                    # Prepare point for batch insert
                    schema_point = {
                        'embedding': embedding,
                        'payload': {
                            'table_name': table_name,
                            'schema_text': schema_text,
                            'table_data': table_data,
                            'catalog_info': catalog_info,
                            'query_examples_count': len(table_data.get('examples', [])),
                            'has_query_examples': len(table_data.get('examples', [])) > 0,
                            'ingestion_time': datetime.now().isoformat()
                        }
                    }
                    schema_points.append(schema_point)
                    processed_tables += 1

                    # Log query examples found
                    examples_count = len(table_data.get('examples', []))
                    if examples_count > 0:
                        logger.info(f"  ✅ Found {examples_count} query examples for {table_name}")
                    else:
                        logger.warning(f"  ⚠️  No query examples found for {table_name}")
                else:
                    logger.warning(f"Table file not found: {table_file}")

            # Batch insert all schemas
            if schema_points:
                await vector_store.store_multiple_schemas(schema_points)
                logger.info(f"Successfully ingested {processed_tables} tables with enhanced query examples")

            return SchemaIngestionStatus(
                status="success",
                message=f"Enhanced schema with query examples ingested successfully",
                processed_tables=processed_tables,
                catalog_loaded=len(catalog_data) > 0,
                ingestion_time=datetime.now().isoformat()
            )

        except Exception as e:
            logger.error(f"Error during enhanced schema ingestion: {e}")
            return SchemaIngestionStatus(
                status="error",
                message=f"Enhanced schema ingestion failed: {str(e)}",
                processed_tables=0,
                catalog_loaded=False,
                ingestion_time=datetime.now().isoformat()
            )

    def _process_table_schema_with_examples(self, table_data: Dict[str, Any], table_name: str,
                                            catalog_info: Dict[str, Any]) -> str:
        """Process table schema into searchable text including query examples"""
        schema_text = f"Table: {table_name}\n"

        # Handle your specific data format
        if 'display_name' in table_data:
            schema_text += f"Display Name: {table_data['display_name']}\n"

        if 'alias' in table_data:
            schema_text += f"Alias: {table_data['alias']}\n"

        # Add table description
        if 'description' in table_data:
            schema_text += f"Description: {table_data['description']}\n"

        # Add catalog description if different
        if 'description' in catalog_info and catalog_info['description'] != table_data.get('description'):
            schema_text += f"Additional Info: {catalog_info['description']}\n"

        # Process fields
        if 'fields' in table_data:
            schema_text += "\nFields/Columns:\n"
            for field_name, field_description in table_data['fields'].items():
                schema_text += f"- {field_name}: {field_description}\n"

        # Process joins (relationships)
        if 'joins' in table_data:
            schema_text += "\nTable Relationships/Joins:\n"
            for join_table, join_conditions in table_data['joins'].items():
                if isinstance(join_conditions, list):
                    for condition in join_conditions:
                        schema_text += f"- JOIN {join_table}: {condition}\n"
                else:
                    schema_text += f"- JOIN {join_table}: {join_conditions}\n"

        # Process indexes
        if 'Indexes' in table_data:
            schema_text += "\nDatabase Indexes:\n"
            for index_name, index_description in table_data['Indexes'].items():
                schema_text += f"- {index_name}: {index_description}\n"

        # *** NEW: Process Query Examples ***
        if 'examples' in table_data and table_data['examples']:
            schema_text += "\nSQL Query Examples and Patterns:\n"
            schema_text += "=" * 40 + "\n"

            for i, example in enumerate(table_data['examples'], 1):
                query = example.get('query', '')
                description = example.get('description', '')
                parameters = example.get('parameters', {})

                schema_text += f"\nExample {i}: {description}\n"
                schema_text += f"SQL Pattern:\n{query}\n"

                if parameters:
                    schema_text += "Parameters:\n"
                    for param_name, param_desc in parameters.items():
                        schema_text += f"  - {param_name}: {param_desc}\n"

                # Extract SQL patterns for better understanding
                sql_patterns = self._extract_sql_patterns(query)
                if sql_patterns:
                    schema_text += f"SQL Techniques Used: {', '.join(sql_patterns)}\n"

                schema_text += "-" * 30 + "\n"

        # Add business context from catalog
        business_context = self._process_business_context(catalog_info)
        if business_context:
            schema_text += f"\nBusiness Context:\n{business_context}\n"

        # Add metadata
        metadata = self._process_metadata(catalog_info)
        if metadata:
            schema_text += f"\nMetadata:\n{metadata}\n"

        # Add usage summary based on examples
        if 'examples' in table_data and table_data['examples']:
            usage_summary = self._generate_usage_summary(table_data['examples'])
            schema_text += f"\nCommon Usage Patterns:\n{usage_summary}\n"

        return schema_text

    def _extract_sql_patterns(self, query: str) -> List[str]:
        """Extract SQL patterns and techniques from example queries"""
        patterns = []
        query_upper = query.upper()

        # Check for SQL techniques
        if 'JOIN' in query_upper:
            patterns.append('JOINS')
        if 'NOLOCK' in query_upper:
            patterns.append('NOLOCK_HINTS')
        if 'ORDER BY' in query_upper:
            patterns.append('SORTING')
        if 'BETWEEN' in query_upper:
            patterns.append('DATE_RANGES')
        if 'AND' in query_upper and 'OR' in query_upper:
            patterns.append('COMPLEX_CONDITIONS')
        if any(op in query_upper for op in ['=', '<>', '>', '<', '>=', '<=']):
            patterns.append('FILTERING')
        if 'GROUP BY' in query_upper:
            patterns.append('AGGREGATION')
        if any(func in query_upper for func in ['COUNT', 'SUM', 'AVG', 'MAX', 'MIN']):
            patterns.append('FUNCTIONS')

        return patterns

    def _generate_usage_summary(self, examples: List[Dict[str, Any]]) -> str:
        """Generate a summary of common usage patterns from examples"""
        summary = []

        # Analyze common patterns
        join_tables = set()
        common_filters = set()
        date_patterns = []

        for example in examples:
            query = example.get('query', '').upper()
            description = example.get('description', '')

            # Extract joined tables
            if 'JOIN' in query:
                # Simple extraction - could be more sophisticated
                words = query.split()
                for i, word in enumerate(words):
                    if word == 'JOIN' and i + 1 < len(words):
                        table = words[i + 1].replace('(NOLOCK)', '').strip()
                        join_tables.add(table)

            # Extract common filter patterns
            if 'ARDATE' in query:
                common_filters.add('date_filtering')
            if 'ARTEST' in query:
                common_filters.add('test_code_filtering')
            if 'ARORDNO' in query:
                common_filters.add('order_number_filtering')
            if 'ARRESSTAT' in query:
                common_filters.add('result_status_filtering')

            # Note usage patterns
            if 'patient' in description.lower():
                summary.append("- Patient-specific queries")
            if 'date' in description.lower():
                summary.append("- Date-based filtering")
            if 'test' in description.lower():
                summary.append("- Test result retrieval")

        if join_tables:
            summary.append(f"- Commonly joined with: {', '.join(join_tables)}")

        if common_filters:
            filter_desc = {
                'date_filtering': 'Date-based queries',
                'test_code_filtering': 'Test code filtering',
                'order_number_filtering': 'Order-based queries',
                'result_status_filtering': 'Result status filtering'
            }
            filters = [filter_desc.get(f, f) for f in common_filters]
            summary.append(f"- Common filters: {', '.join(filters)}")

        return '\n'.join(summary) if summary else "- General data retrieval queries"

    async def _load_catalog_index(self) -> Dict[str, Any]:
        """Load the catalog index file"""
        catalog_path = self.kb_path / "catalog_index.jsonl"
        catalog_data = {}

        try:
            if catalog_path.exists():
                with open(catalog_path, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if line:
                            try:
                                entry = json.loads(line)
                                table_name = entry.get('table_name')
                                if table_name:
                                    catalog_data[table_name] = entry
                            except json.JSONDecodeError as e:
                                logger.warning(f"Invalid JSON in catalog_index.jsonl at line {line_num}: {e}")
            else:
                logger.warning(f"Catalog index file not found: {catalog_path}")

        except Exception as e:
            logger.error(f"Error loading catalog index: {e}")

        return catalog_data

    def _load_table_file(self, table_file: Path) -> Dict[str, Any]:
        """Load a single table JSON file"""
        try:
            with open(table_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in file {table_file}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error loading table file {table_file}: {e}")
            return {}

    def _process_business_context(self, catalog_info: Dict[str, Any]) -> str:
        """Process business context information"""
        context_text = ""

        business_fields = ['business_purpose', 'data_source', 'update_frequency', 'owner', 'usage_notes']

        for field in business_fields:
            if field in catalog_info:
                field_name = field.replace('_', ' ').title()
                context_text += f"- {field_name}: {catalog_info[field]}\n"

        return context_text.strip()

    def _process_metadata(self, catalog_info: Dict[str, Any]) -> str:
        """Process metadata information"""
        metadata_text = ""

        metadata_fields = ['created_date', 'last_modified', 'record_count', 'data_quality', 'compliance_notes']

        for field in metadata_fields:
            if field in catalog_info:
                field_name = field.replace('_', ' ').title()
                metadata_text += f"- {field_name}: {catalog_info[field]}\n"

        return metadata_text.strip()

    def validate_poc_tables(self) -> Dict[str, Any]:
        """Validate that all POC table files exist and are readable"""
        validation_result = {
            'valid_tables': [],
            'missing_tables': [],
            'invalid_tables': [],
            'tables_with_examples': [],
            'total_poc_tables': len(self.poc_tables)
        }

        for table_name in self.poc_tables:
            table_file = self.kb_path / f"{table_name}.json"

            if not table_file.exists():
                validation_result['missing_tables'].append(table_name)
            else:
                try:
                    table_data = self._load_table_file(table_file)
                    if table_data:
                        validation_result['valid_tables'].append(table_name)

                        # Check for query examples
                        if 'examples' in table_data and table_data['examples']:
                            validation_result['tables_with_examples'].append({
                                'table': table_name,
                                'example_count': len(table_data['examples'])
                            })
                    else:
                        validation_result['invalid_tables'].append(table_name)
                except Exception as e:
                    logger.error(f"Error validating table {table_name}: {e}")
                    validation_result['invalid_tables'].append(table_name)

        return validation_result

    def get_table_summary(self, table_name: str) -> Dict[str, Any]:
        """Get a summary of a specific table including query examples"""
        table_file = self.kb_path / f"{table_name}.json"

        if not table_file.exists():
            return {"error": f"Table file not found: {table_name}"}

        try:
            table_data = self._load_table_file(table_file)
            if not table_data:
                return {"error": f"Failed to load table data: {table_name}"}

            summary = {
                "table_name": table_name,
                "has_description": "description" in table_data,
                "field_count": len(table_data.get('fields', {})),
                "has_joins": "joins" in table_data and len(table_data['joins']) > 0,
                "has_indexes": "Indexes" in table_data and len(table_data['Indexes']) > 0,
                "query_examples_count": len(table_data.get('examples', [])),
                "has_query_examples": len(table_data.get('examples', [])) > 0,
                "display_name": table_data.get('display_name', ''),
                "alias": table_data.get('alias', '')
            }

            # Query examples summary
            if 'examples' in table_data and table_data['examples']:
                example_descriptions = [ex.get('description', 'No description') for ex in table_data['examples']]
                summary['example_descriptions'] = example_descriptions
                summary['sql_patterns_used'] = []

                for example in table_data['examples']:
                    patterns = self._extract_sql_patterns(example.get('query', ''))
                    summary['sql_patterns_used'].extend(patterns)

                summary['sql_patterns_used'] = list(set(summary['sql_patterns_used']))

            # Field types summary (extract from field descriptions)
            if 'fields' in table_data:
                field_types = {}
                for field_name, field_desc in table_data['fields'].items():
                    # Extract type from description (e.g., "Order Date (int)" -> "int")
                    if '(' in field_desc and ')' in field_desc:
                        field_type = field_desc.split('(')[-1].split(')')[0]
                        field_types[field_type] = field_types.get(field_type, 0) + 1
                summary['field_types'] = field_types

            return summary

        except Exception as e:
            logger.error(f"Error getting table summary for {table_name}: {e}")
            return {"error": f"Error processing table: {str(e)}"}

    def get_all_table_summaries(self) -> Dict[str, Any]:
        """Get summaries of all POC tables"""
        summaries = {}

        for table_name in self.poc_tables:
            summaries[table_name] = self.get_table_summary(table_name)

        return summaries