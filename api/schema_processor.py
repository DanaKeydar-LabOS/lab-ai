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
            logger.info("Starting schema ingestion...")

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

                    # Process schema into searchable text
                    schema_text = self._process_table_schema(table_data, table_name, catalog_info)

                    # Generate embedding
                    embedding = await sql_generator.get_embedding(schema_text)

                    # Prepare point for batch insert (don't include 'id' here, let vector_store generate it)
                    schema_point = {
                        'embedding': embedding,
                        'payload': {
                            'table_name': table_name,
                            'schema_text': schema_text,
                            'table_data': table_data,
                            'catalog_info': catalog_info,
                            'ingestion_time': datetime.now().isoformat()
                        }
                    }
                    schema_points.append(schema_point)
                    processed_tables += 1
                else:
                    logger.warning(f"Table file not found: {table_file}")

            # Batch insert all schemas
            if schema_points:
                await vector_store.store_multiple_schemas(schema_points)
                logger.info(f"Successfully ingested {processed_tables} tables")

            return SchemaIngestionStatus(
                status="success",
                message=f"Schema ingested successfully",
                processed_tables=processed_tables,
                catalog_loaded=len(catalog_data) > 0,
                ingestion_time=datetime.now().isoformat()
            )

        except Exception as e:
            logger.error(f"Error during schema ingestion: {e}")
            return SchemaIngestionStatus(
                status="error",
                message=f"Schema ingestion failed: {str(e)}",
                processed_tables=0,
                catalog_loaded=False,
                ingestion_time=datetime.now().isoformat()
            )

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

    def _process_table_schema(self, table_data: Dict[str, Any], table_name: str,
                              catalog_info: Dict[str, Any]) -> str:
        """Process table schema into searchable text for your data format"""
        schema_text = f"Table: {table_name}\n"

        # Handle your specific data format
        # Add display name and alias
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

        # Process fields (your format uses 'fields' instead of 'columns')
        if 'fields' in table_data:
            schema_text += "\nFields:\n"
            for field_name, field_description in table_data['fields'].items():
                schema_text += f"- {field_name}: {field_description}\n"

        # Process joins (relationships)
        if 'joins' in table_data:
            schema_text += "\nJoins/Relationships:\n"
            for join_table, join_conditions in table_data['joins'].items():
                if isinstance(join_conditions, list):
                    for condition in join_conditions:
                        schema_text += f"- {join_table}: {condition}\n"
                else:
                    schema_text += f"- {join_table}: {join_conditions}\n"

        # Process indexes if available
        if 'Indexes' in table_data:
            schema_text += "\nIndexes:\n"
            for index_name, index_description in table_data['Indexes'].items():
                schema_text += f"- {index_name}: {index_description}\n"

        # Add examples if available
        if 'examples' in table_data and table_data['examples']:
            schema_text += "\nExamples:\n"
            for i, example in enumerate(table_data['examples'][:3]):  # Limit to 3 examples
                schema_text += f"Example {i + 1}: {example}\n"

        # Add business context from catalog
        business_context = self._process_business_context(catalog_info)
        if business_context:
            schema_text += f"\nBusiness Context:\n{business_context}\n"

        # Add metadata
        metadata = self._process_metadata(catalog_info)
        if metadata:
            schema_text += f"\nMetadata:\n{metadata}\n"

        return schema_text

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
                    else:
                        validation_result['invalid_tables'].append(table_name)
                except Exception as e:
                    logger.error(f"Error validating table {table_name}: {e}")
                    validation_result['invalid_tables'].append(table_name)

        return validation_result

    def get_table_summary(self, table_name: str) -> Dict[str, Any]:
        """Get a summary of a specific table"""
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
                "has_examples": "examples" in table_data and len(table_data['examples']) > 0,
                "display_name": table_data.get('display_name', ''),
                "alias": table_data.get('alias', '')
            }

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