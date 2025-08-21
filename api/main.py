from fastapi import FastAPI, HTTPException
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from config import settings
from models import QueryRequest, SQLResponse, SchemaIngestionStatus
from database import DatabaseManager, QueryCache
from vector_store import VectorStore
from sql_generator import SQLGenerator
from schema_processor import SchemaProcessor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Lab Text-to-SQL RAG API",
    description="Generate SQL queries for lab database insights",
    version="1.0.0"
)

# Global instances
vector_store = None
sql_generator = None
db_manager = None
query_cache = None
schema_processor = None


@app.on_event("startup")
async def startup_event():
    """Initialize all components on startup"""
    global vector_store, sql_generator, db_manager, query_cache, schema_processor

    try:
        logger.info("Starting Lab RAG API...")

        # Initialize vector store
        vector_store = VectorStore(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            collection_name=settings.COLLECTION_NAME
        )
        await vector_store.initialize()

        # Initialize SQL generator
        sql_generator = SQLGenerator(
            ollama_host=settings.OLLAMA_HOST,
            ollama_port=settings.OLLAMA_PORT,
            embedding_model=settings.EMBEDDING_MODEL,
            chat_model=settings.CHAT_MODEL
        )
        await sql_generator.initialize()

        # Initialize database manager
        db_manager = DatabaseManager(settings.DB_CONFIG)

        # Test database connection
        if await db_manager.test_connection():
            logger.info("Database connection successful")
        else:
            logger.warning("Database connection test failed")

        # Initialize query cache
        query_cache = QueryCache(max_size=50, ttl_seconds=300)

        # Initialize schema processor
        schema_processor = SchemaProcessor(
            kb_path=settings.KB_PATH,
            poc_tables=settings.POC_TABLES
        )

        logger.info("All components initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize components: {e}")
        raise


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Lab Text-to-SQL RAG API is running",
        "version": "1.0.0",
        "poc_tables_count": len(settings.POC_TABLES)
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check vector store
        vector_status = await vector_store.health_check()

        # Check SQL generator (Ollama)
        sql_gen_status = await sql_generator.health_check()

        # Check database
        db_status = await db_manager.test_connection() if db_manager else False

        return {
            "status": "healthy",
            "components": {
                "vector_store": "connected" if vector_status else "disconnected",
                "sql_generator": "connected" if sql_gen_status else "disconnected",
                "database": "connected" if db_status else "disconnected"
            },
            "poc_tables": settings.POC_TABLES,
            "models": {
                "embedding": settings.EMBEDDING_MODEL,
                "chat": settings.CHAT_MODEL
            }
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Health check failed: {str(e)}")


@app.post("/ingest/schema", response_model=SchemaIngestionStatus)
async def ingest_database_schema():
    """Ingest database schema into vector store"""
    try:
        return await schema_processor.ingest_schema(vector_store, sql_generator)
    except Exception as e:
        logger.error(f"Schema ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Schema ingestion failed: {str(e)}")


@app.post("/query/sql", response_model=SQLResponse)
async def generate_sql_from_question(request: QueryRequest):
    """Generate SQL query from natural language question"""
    try:
        # Find relevant tables
        relevant_tables = await vector_store.find_relevant_tables(
            question=request.question,
            embedding_generator=sql_generator.get_embedding,
            limit=5
        )

        if not relevant_tables:
            raise HTTPException(
                status_code=404,
                detail="No relevant tables found for your question"
            )

        # Generate SQL query
        sql_result = await sql_generator.generate_sql(request.question, relevant_tables)

        if not sql_result['sql_query']:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate SQL query"
            )

        # Validate the query - FIX: Access attributes properly
        validation = sql_generator.validate_sql(sql_result['sql_query'])
        if not validation.is_valid:  # Use .is_valid instead of ['is_valid']
            raise HTTPException(
                status_code=400,
                detail=f"Generated SQL is invalid: {'; '.join(validation.errors)}"  # Use .errors
            )

        # Execute query if requested
        results = None
        row_count = None
        executed = False
        error = None

        if request.execute_query:
            # Check cache first
            cached_result = query_cache.get(sql_result['sql_query']) if query_cache else None

            if cached_result:
                logger.info("Using cached query result")
                execution_result = cached_result
            else:
                execution_result = await db_manager.execute_query(sql_result['sql_query'])

                # Cache successful results
                if query_cache and execution_result.success:  # Use .success instead of ['success']
                    query_cache.set(sql_result['sql_query'], execution_result)

            executed = True

            if execution_result.success:  # Use .success instead of ['success']
                results = execution_result.results  # Use .results
                row_count = execution_result.row_count  # Use .row_count
            else:
                error = execution_result.error  # Use .error

        return SQLResponse(
            question=request.question,
            generated_sql=sql_result['sql_query'],
            explanation=sql_result['explanation'],
            tables_used=sql_result['tables_used'],
            executed=executed,
            results=results,
            row_count=row_count,
            error=error
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing question: {e}")
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")


@app.get("/tables/available")
async def get_available_tables():
    """Get list of available POC tables"""
    return {
        "poc_tables": settings.POC_TABLES,
        "total_count": len(settings.POC_TABLES),
        "note": "These are the tables available in this POC version"
    }


@app.get("/tables/schema/{table_name}")
async def get_table_schema(table_name: str):
    """Get detailed schema for a specific table"""
    if table_name not in settings.POC_TABLES:
        raise HTTPException(
            status_code=404,
            detail=f"Table {table_name} not available in POC. Available tables: {settings.POC_TABLES}"
        )

    try:
        schema_info = await vector_store.get_table_schema(
            table_name=table_name,
            embedding_generator=sql_generator.get_embedding
        )

        if not schema_info:
            raise HTTPException(
                status_code=404,
                detail=f"Schema for table {table_name} not found. Run schema ingestion first."
            )

        return schema_info

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving table schema: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve schema: {str(e)}")


@app.delete("/schema/reset")
async def reset_schema():
    """Reset the schema collection"""
    try:
        await vector_store.reset_collection()
        return {"message": "Schema collection reset successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset schema: {str(e)}")


@app.get("/cache/stats")
async def get_cache_stats():
    """Get query cache statistics"""
    if not query_cache:
        return {"message": "Cache not initialized"}

    return query_cache.get_stats()


@app.delete("/cache/clear")
async def clear_cache():
    """Clear query cache"""
    if query_cache:
        query_cache.clear()
        return {"message": "Cache cleared successfully"}
    else:
        return {"message": "Cache not initialized"}


# Debug endpoints
@app.get("/debug/kb-files")
async def debug_kb_files():
    """Debug endpoint to check KB files status"""
    try:
        from pathlib import Path

        kb_path = Path(settings.KB_PATH)

        if not kb_path.exists():
            return {"error": f"KB directory does not exist: {kb_path}"}

        file_status = {}
        missing_files = []
        invalid_files = []

        for table_name in settings.POC_TABLES:
            table_file = kb_path / f"{table_name}.json"

            if not table_file.exists():
                missing_files.append(table_name)
                file_status[table_name] = {"status": "missing", "file_path": str(table_file)}
                continue

            try:
                import json
                with open(table_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                file_status[table_name] = {
                    "status": "valid",
                    "file_path": str(table_file),
                    "file_size": table_file.stat().st_size,
                    "field_count": len(data.get('fields', {})),
                    "has_description": 'description' in data,
                    "has_joins": 'joins' in data
                }

            except json.JSONDecodeError as e:
                invalid_files.append(table_name)
                file_status[table_name] = {
                    "status": "invalid_json",
                    "error": str(e),
                    "file_path": str(table_file)
                }
            except Exception as e:
                invalid_files.append(table_name)
                file_status[table_name] = {
                    "status": "error",
                    "error": str(e),
                    "file_path": str(table_file)
                }

        return {
            "kb_path": str(kb_path),
            "total_poc_tables": len(settings.POC_TABLES),
            "valid_files": len([f for f in file_status.values() if f["status"] == "valid"]),
            "missing_files": len(missing_files),
            "invalid_files": len(invalid_files),
            "file_details": file_status,
            "missing_table_names": missing_files,
            "invalid_table_names": invalid_files
        }

    except Exception as e:
        logger.error(f"Debug KB files error: {e}")
        raise HTTPException(status_code=500, detail=f"Debug failed: {str(e)}")


@app.get("/debug/vector-store")
async def debug_vector_store():
    """Debug endpoint to check vector store status"""
    try:
        if not vector_store:
            return {"error": "Vector store not initialized"}

        # Check health
        is_healthy = await vector_store.health_check()

        # Get collection info
        collection_info = await vector_store.get_collection_info()

        # Get all stored tables
        stored_tables = await vector_store.get_all_tables()

        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "collection_info": collection_info,
            "stored_tables_count": len(stored_tables),
            "stored_tables": stored_tables,
            "missing_poc_tables": [t for t in settings.POC_TABLES if t not in stored_tables]
        }

    except Exception as e:
        logger.error(f"Debug vector store error: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@app.get("/debug/ollama")
async def debug_ollama():
    """Debug endpoint to check Ollama status"""
    try:
        if not sql_generator:
            return {"error": "SQL generator not initialized"}

        # Check health
        is_healthy = await sql_generator.health_check()

        # Get available models
        available_models = await sql_generator.get_available_models()

        # Test embedding generation
        test_embedding = None
        embedding_error = None
        try:
            test_text = "test schema for table experiments"
            test_embedding = await sql_generator.get_embedding(test_text)
            embedding_dimensions = len(test_embedding) if test_embedding else 0
        except Exception as e:
            embedding_error = str(e)
            embedding_dimensions = 0

        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "available_models": available_models,
            "required_models": {
                "embedding": settings.EMBEDDING_MODEL,
                "chat": settings.CHAT_MODEL
            },
            "models_available": {
                "embedding": settings.EMBEDDING_MODEL in available_models,
                "chat": settings.CHAT_MODEL in available_models
            },
            "test_embedding": {
                "success": test_embedding is not None,
                "dimensions": embedding_dimensions,
                "error": embedding_error
            }
        }

    except Exception as e:
        logger.error(f"Debug Ollama error: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@app.post("/debug/test-ingestion")
async def debug_test_ingestion():
    """Debug endpoint to test schema ingestion with detailed logging"""
    try:
        if not all([vector_store, sql_generator, schema_processor]):
            missing = []
            if not vector_store: missing.append("vector_store")
            if not sql_generator: missing.append("sql_generator")
            if not schema_processor: missing.append("schema_processor")
            return {"error": f"Components not initialized: {missing}"}

        # Test with just one table first
        test_table = None
        from pathlib import Path
        kb_path = Path(settings.KB_PATH)

        for table_name in settings.POC_TABLES[:3]:  # Test first 3 tables
            table_file = kb_path / f"{table_name}.json"
            if table_file.exists():
                test_table = table_name
                break

        if not test_table:
            return {"error": "No valid POC table files found for testing"}

        logger.info(f"Testing ingestion with table: {test_table}")

        # Step 1: Load and process single table
        table_file = kb_path / f"{test_table}.json"
        import json
        with open(table_file, 'r', encoding='utf-8') as f:
            table_data = json.load(f)

        # Step 2: Process schema text
        schema_text = schema_processor._process_table_schema(table_data, test_table, {})

        # Step 3: Generate embedding
        embedding = await sql_generator.get_embedding(schema_text)

        # Step 4: Store in vector database
        point_id = await vector_store.store_table_schema(
            table_name=test_table,
            schema_text=schema_text,
            table_data=table_data,
            catalog_info={},
            embedding=embedding
        )

        # Step 5: Test retrieval
        test_question = f"show me data from {test_table}"
        relevant_tables = await vector_store.find_relevant_tables(
            question=test_question,
            embedding_generator=sql_generator.get_embedding,
            limit=1
        )

        return {
            "status": "success",
            "test_table": test_table,
            "schema_text_length": len(schema_text),
            "embedding_dimensions": len(embedding),
            "point_id": point_id,
            "retrieval_test": {
                "question": test_question,
                "found_tables": len(relevant_tables),
                "top_match": relevant_tables[0] if relevant_tables else None
            },
            "schema_preview": schema_text[:300] + "..." if len(schema_text) > 300 else schema_text
        }

    except Exception as e:
        logger.error(f"Debug test ingestion error: {e}")
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


# Add this debug endpoint to your main.py file

@app.get("/debug/query-examples")
async def debug_query_examples():
    """Debug endpoint to show all query examples in the system"""
    try:
        from pathlib import Path
        import json

        kb_path = Path(settings.KB_PATH)
        all_examples = {}

        for table_name in settings.POC_TABLES:
            table_file = kb_path / f"{table_name}.json"

            if table_file.exists():
                try:
                    with open(table_file, 'r', encoding='utf-8') as f:
                        table_data = json.load(f)

                    examples = table_data.get('examples', [])
                    if examples:
                        all_examples[table_name] = {
                            'count': len(examples),
                            'examples': examples
                        }

                except Exception as e:
                    logger.error(f"Error loading {table_name}: {e}")

        # Summary statistics
        total_examples = sum(info['count'] for info in all_examples.values())
        tables_with_examples = len(all_examples)

        return {
            "summary": {
                "total_tables_with_examples": tables_with_examples,
                "total_query_examples": total_examples,
                "tables_without_examples": len(settings.POC_TABLES) - tables_with_examples
            },
            "examples_by_table": all_examples
        }

    except Exception as e:
        logger.error(f"Error getting query examples: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get query examples: {str(e)}")


@app.post("/debug/test-enhanced-query")
async def debug_test_enhanced_query(request: QueryRequest):
    """Test the enhanced query generation with detailed debugging"""
    try:
        # Find relevant tables
        relevant_tables = await vector_store.find_relevant_tables(
            question=request.question,
            embedding_generator=sql_generator.get_embedding,
            limit=3
        )

        if not relevant_tables:
            return {"error": "No relevant tables found"}

        # Extract query examples from relevant tables
        query_examples = []
        for table_info in relevant_tables:
            table_data = table_info.get('table_data', {})
            if 'examples' in table_data:
                for example in table_data['examples']:
                    query_examples.append({
                        'table': table_info['table_name'],
                        'query': example.get('query', ''),
                        'description': example.get('description', ''),
                        'parameters': example.get('parameters', {})
                    })

        # Generate SQL
        sql_result = await sql_generator.generate_sql(request.question, relevant_tables)

        return {
            "question": request.question,
            "relevant_tables": [t['table_name'] for t in relevant_tables],
            "found_query_examples": len(query_examples),
            "query_examples_used": query_examples[:3],  # Show first 3
            "generated_sql": sql_result.get('generated_sql', ''),
            "explanation": sql_result.get('explanation', ''),
            "tables_used": sql_result.get('tables_used', []),
            "schema_context_length": sum(len(t['schema_text']) for t in relevant_tables)
        }

    except Exception as e:
        logger.error(f"Error in enhanced query test: {e}")
        return {
            "error": str(e),
            "question": request.question
        }


@app.post("/debug/raw-llm-response")
async def debug_raw_llm_response(request: QueryRequest):
    """Debug endpoint to see raw LLM response for SQL generation"""
    try:
        # Find relevant tables
        relevant_tables = await vector_store.find_relevant_tables(
            question=request.question,
            embedding_generator=sql_generator.get_embedding,
            limit=3
        )

        if not relevant_tables:
            return {"error": "No relevant tables found"}

        # Extract query examples
        query_examples = []
        for table_info in relevant_tables:
            table_data = table_info.get('table_data', {})
            if 'examples' in table_data:
                for example in table_data['examples']:
                    query_examples.append({
                        'table': table_info['table_name'],
                        'query': example.get('query', ''),
                        'description': example.get('description', ''),
                        'parameters': example.get('parameters', {})
                    })

        # Prepare schema context
        schema_context = ""
        table_names = []
        for table_info in relevant_tables:
            table_names.append(table_info['table_name'])
            schema_context += f"\n{table_info['schema_text']}\n" + "=" * 50 + "\n"

        # Create the prompt (same as in sql_generator)
        prompt = sql_generator._create_enhanced_sql_prompt(
            request.question, schema_context, table_names, query_examples
        )

        # Get raw LLM response
        response = await sql_generator.client.generate(
            model=sql_generator.chat_model,
            prompt=prompt,
            stream=False
        )

        raw_response = response['response']

        # Also show parsing result
        parsed_result = sql_generator._parse_sql_response(raw_response)

        return {
            "question": request.question,
            "relevant_tables": table_names,
            "prompt_length": len(prompt),
            "raw_llm_response": raw_response,
            "parsed_sql": parsed_result['sql_query'],
            "parsed_explanation": parsed_result['explanation'],
            "parsed_tables": parsed_result['tables_used'],
            "prompt_preview": prompt[:500] + "..." if len(prompt) > 500 else prompt
        }

    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "question": request.question
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)