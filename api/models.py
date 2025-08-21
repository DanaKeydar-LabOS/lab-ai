from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class QueryRequest(BaseModel):
    """Request model for SQL query generation"""
    question: str = Field(..., description="Natural language question about lab data")
    execute_query: Optional[bool] = Field(False, description="Whether to execute the generated SQL")
    limit: Optional[int] = Field(100, description="Maximum number of rows to return")

class SQLResponse(BaseModel):
    """Response model for SQL query generation"""
    question: str = Field(..., description="Original question")
    generated_sql: str = Field(..., description="Generated SQL query")
    explanation: str = Field(..., description="Explanation of what the query does")
    tables_used: List[str] = Field(..., description="List of tables used in the query")
    executed: bool = Field(..., description="Whether the query was executed")
    results: Optional[List[Dict[str, Any]]] = Field(None, description="Query results if executed")
    row_count: Optional[int] = Field(None, description="Number of rows returned")
    error: Optional[str] = Field(None, description="Error message if execution failed")
    execution_time: Optional[float] = Field(None, description="Query execution time in seconds")

class SchemaIngestionStatus(BaseModel):
    """Status model for schema ingestion"""
    status: str = Field(..., description="Ingestion status: success, error, or in_progress")
    message: str = Field(..., description="Status message")
    processed_tables: int = Field(..., description="Number of tables processed")
    catalog_loaded: bool = Field(..., description="Whether catalog index was loaded")
    ingestion_time: Optional[str] = Field(None, description="Ingestion timestamp")

class TableInfo(BaseModel):
    """Model for table schema information"""
    table_name: str = Field(..., description="Name of the table")
    description: Optional[str] = Field(None, description="Table description")
    columns: List[Dict[str, Any]] = Field(..., description="Column definitions")
    relationships: Optional[List[str]] = Field(None, description="Table relationships")
    sample_data: Optional[List[Dict[str, Any]]] = Field(None, description="Sample data rows")

class ColumnInfo(BaseModel):
    """Model for column information"""
    name: str = Field(..., description="Column name")
    type: str = Field(..., description="Column data type")
    description: Optional[str] = Field(None, description="Column description")
    nullable: Optional[bool] = Field(None, description="Whether column allows NULL values")
    primary_key: Optional[bool] = Field(None, description="Whether column is primary key")
    foreign_key: Optional[str] = Field(None, description="Foreign key reference if applicable")

class QueryValidation(BaseModel):
    """Model for SQL query validation results"""
    is_valid: bool = Field(..., description="Whether the query is valid")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")

class DatabaseExecutionResult(BaseModel):
    """Model for database query execution results"""
    success: bool = Field(..., description="Whether execution was successful")
    results: Optional[List[Dict[str, Any]]] = Field(None, description="Query results")
    row_count: int = Field(..., description="Number of rows returned")
    columns: Optional[List[str]] = Field(None, description="Column names")
    execution_time: float = Field(..., description="Execution time in seconds")
    error: Optional[str] = Field(None, description="Error message if failed")

class HealthStatus(BaseModel):
    """Model for health check status"""
    status: str = Field(..., description="Overall status: healthy or unhealthy")
    components: Dict[str, str] = Field(..., description="Status of individual components")
    poc_tables: List[str] = Field(..., description="Available POC tables")
    models: Dict[str, str] = Field(..., description="AI models being used")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

class CacheStats(BaseModel):
    """Model for cache statistics"""
    size: int = Field(..., description="Number of cached items")
    max_size: int = Field(..., description="Maximum cache size")
    hit_rate: float = Field(..., description="Cache hit rate percentage")
    total_requests: int = Field(..., description="Total cache requests")
    hits: int = Field(..., description="Number of cache hits")
    misses: int = Field(..., description="Number of cache misses")

class RelevantTable(BaseModel):
    """Model for relevant table information from vector search"""
    table_name: str = Field(..., description="Name of the table")
    schema_text: str = Field(..., description="Full schema text")
    score: float = Field(..., description="Relevance score from vector search")
    table_data: Dict[str, Any] = Field(..., description="Original table data")
    catalog_info: Dict[str, Any] = Field(default_factory=dict, description="Catalog metadata")

class SQLGenerationResult(BaseModel):
    """Model for SQL generation results"""
    sql_query: str = Field(..., description="Generated SQL query")
    explanation: str = Field(..., description="Explanation of the query")
    tables_used: List[str] = Field(..., description="Tables used in the query")
    confidence: Optional[float] = Field(None, description="Confidence score for the query")
    alternatives: Optional[List[str]] = Field(None, description="Alternative query suggestions")