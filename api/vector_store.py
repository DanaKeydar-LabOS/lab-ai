import logging
import hashlib
import uuid
from typing import List, Dict, Any, Optional, Callable
from qdrant_client import QdrantClient, models
from qdrant_client.models import Distance, VectorParams
from config import settings

logger = logging.getLogger(__name__)


class VectorStore:
    """Vector store manager using Qdrant for schema storage and retrieval"""

    def __init__(self, host: str, port: int, collection_name: str):
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.client = None

    def _generate_point_id(self, table_name: str) -> str:
        """Generate a valid UUID point ID from table name"""
        # Create a deterministic UUID based on table name
        namespace = uuid.UUID('12345678-1234-5678-1234-123456789abc')
        point_id = str(uuid.uuid5(namespace, f"table_{table_name}"))
        return point_id

    async def initialize(self):
        """Initialize Qdrant client and ensure collection exists"""
        try:
            self.client = QdrantClient(host=self.host, port=self.port)
            logger.info(f"Connected to Qdrant at {self.host}:{self.port}")

            # Check if collection exists, create if not
            collections = self.client.get_collections()
            collection_names = [col.name for col in collections.collections]

            if self.collection_name not in collection_names:
                await self.create_collection()
            else:
                logger.info(f"Collection {self.collection_name} already exists")

        except Exception as e:
            logger.error(f"Failed to initialize Qdrant client: {e}")
            raise

    async def create_collection(self):
        """Create or recreate the collection"""
        try:
            # Delete existing collection if it exists
            try:
                self.client.delete_collection(self.collection_name)
                logger.info(f"Deleted existing collection: {self.collection_name}")
            except:
                pass

            # Create new collection
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=settings.VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Created collection: {self.collection_name}")

        except Exception as e:
            logger.error(f"Error creating collection: {e}")
            raise

    async def store_table_schema(self, table_name: str, schema_text: str,
                                 table_data: Dict[str, Any], catalog_info: Dict[str, Any],
                                 embedding: List[float]) -> str:
        """Store table schema with its embedding"""
        try:
            point_id = self._generate_point_id(table_name)

            point = models.PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    'table_name': table_name,
                    'schema_text': schema_text,
                    'table_data': table_data,
                    'catalog_info': catalog_info,
                    'ingestion_time': self._get_current_timestamp()
                }
            )

            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )

            logger.info(f"Stored schema for table: {table_name} with ID: {point_id}")
            return point_id

        except Exception as e:
            logger.error(f"Error storing table schema for {table_name}: {e}")
            raise

    async def store_multiple_schemas(self, schema_points: List[Dict[str, Any]]):
        """Store multiple table schemas in batch"""
        try:
            points = []

            for schema_point in schema_points:
                # Generate proper UUID for point ID
                table_name = schema_point['payload']['table_name']
                point_id = self._generate_point_id(table_name)

                point = models.PointStruct(
                    id=point_id,
                    vector=schema_point['embedding'],
                    payload=schema_point['payload']
                )
                points.append(point)
                logger.debug(f"Prepared point for {table_name} with UUID: {point_id}")

            # Batch insert
            batch_size = 100
            for i in range(0, len(points), batch_size):
                batch = points[i:i + batch_size]
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch
                )
                logger.info(f"Inserted batch {i // batch_size + 1}: {len(batch)} points")

            logger.info(f"Successfully stored {len(points)} table schemas")

        except Exception as e:
            logger.error(f"Error storing multiple schemas: {e}")
            raise

    async def find_relevant_tables(self, question: str, embedding_generator: Callable,
                                   limit: int = 5) -> List[Dict[str, Any]]:
        """Find tables relevant to the user's question using vector search"""
        try:
            # Generate query embedding
            query_embedding = await embedding_generator(question)

            # Search in Qdrant
            search_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit,
            )

            # Format results
            relevant_tables = []
            for result in search_results:
                relevant_tables.append({
                    'table_name': result.payload['table_name'],
                    'schema_text': result.payload['schema_text'],
                    'score': result.score,
                    'table_data': result.payload.get('table_data', {}),
                    'catalog_info': result.payload.get('catalog_info', {})
                })

            logger.info(f"Found {len(relevant_tables)} relevant tables for question")
            return relevant_tables

        except Exception as e:
            logger.error(f"Error finding relevant tables: {e}")
            raise

    async def get_table_schema(self, table_name: str, embedding_generator: Callable) -> Optional[Dict[str, Any]]:
        """Get detailed schema for a specific table"""
        try:
            # Search with filter for exact table name
            search_results = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="table_name",
                            match=models.MatchValue(value=table_name)
                        )
                    ]
                ),
                limit=1
            )

            if not search_results[0]:  # search_results is a tuple (points, next_page_offset)
                return None

            table_info = search_results[0][0].payload
            return {
                "table_name": table_info['table_name'],
                "schema_text": table_info['schema_text'],
                "table_data": table_info.get('table_data', {}),
                "catalog_info": table_info.get('catalog_info', {}),
                "ingestion_time": table_info.get('ingestion_time')
            }

        except Exception as e:
            logger.error(f"Error retrieving table schema for {table_name}: {e}")
            raise

    async def get_all_tables(self) -> List[str]:
        """Get list of all stored table names"""
        try:
            # Scroll through all points to get table names
            scroll_result = self.client.scroll(
                collection_name=self.collection_name,
                limit=1000  # Adjust based on expected number of tables
            )

            table_names = []
            for point in scroll_result[0]:
                table_name = point.payload.get('table_name')
                if table_name:
                    table_names.append(table_name)

            return table_names

        except Exception as e:
            logger.error(f"Error getting all tables: {e}")
            return []

    async def delete_table_schema(self, table_name: str):
        """Delete schema for a specific table"""
        try:
            point_id = self._generate_point_id(table_name)
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(
                    points=[point_id]
                )
            )
            logger.info(f"Deleted schema for table: {table_name}")

        except Exception as e:
            logger.error(f"Error deleting table schema for {table_name}: {e}")
            raise

    async def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the collection"""
        try:
            collection_info = self.client.get_collection(self.collection_name)
            return {
                "collection_name": self.collection_name,
                "vectors_count": collection_info.vectors_count,
                "status": collection_info.status,
                "config": collection_info.config.dict() if collection_info.config else None
            }
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {}

    async def reset_collection(self):
        """Reset the collection (delete and recreate)"""
        try:
            await self.create_collection()
            logger.info("Collection reset successfully")
        except Exception as e:
            logger.error(f"Error resetting collection: {e}")
            raise

    async def health_check(self) -> bool:
        """Check if vector store is healthy"""
        try:
            if not self.client:
                return False

            # Try to get collection info
            self.client.get_collection(self.collection_name)
            return True

        except Exception as e:
            logger.error(f"Vector store health check failed: {e}")
            return False

    def _get_current_timestamp(self) -> str:
        """Get current timestamp as ISO string"""
        from datetime import datetime
        return datetime.now().isoformat()