import logging
import time
import hashlib
from typing import Dict, Any, List, Optional
from models import DatabaseExecutionResult, CacheStats

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Database manager for executing SQL queries on lab database"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.driver = config.get('driver', 'postgresql')

    async def execute_query(self, sql_query: str, params: Optional[List] = None) -> DatabaseExecutionResult:
        """Execute SQL query and return results"""
        try:
            if self.driver == 'postgresql':
                return await self._execute_postgresql(sql_query, params)
            elif self.driver == 'mysql':
                return await self._execute_mysql(sql_query, params)
            elif self.driver == 'sqlite':
                return await self._execute_sqlite(sql_query, params)
            elif self.driver == 'sqlserver':
                return await self._execute_sqlserver(sql_query, params)
            else:
                raise ValueError(f"Unsupported database driver: {self.driver}")

        except Exception as e:
            logger.error(f"Database execution error: {e}")
            return DatabaseExecutionResult(
                success=False,
                error=str(e),
                results=None,
                row_count=0,
                execution_time=0
            )

    async def test_connection(self) -> bool:
        """Test database connection"""
        try:
            result = await self.execute_query("SELECT 1 as test")
            return result.success
        except:
            return False

    async def _execute_postgresql(self, sql_query: str, params: Optional[List] = None) -> DatabaseExecutionResult:
        """Execute query on PostgreSQL database"""
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError:
            logger.error("psycopg2 not installed. Install with: pip install psycopg2-binary")
            return DatabaseExecutionResult(
                success=False,
                error='PostgreSQL driver not installed',
                results=None,
                row_count=0,
                execution_time=0
            )

        start_time = time.time()
        conn = None

        try:
            conn = psycopg2.connect(
                host=self.config['host'],
                port=self.config['port'],
                database=self.config['database'],
                user=self.config['user'],
                password=self.config['password'],
                connect_timeout=30
            )

            with conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("SET statement_timeout = '60s'")

                    if params:
                        cursor.execute(sql_query, params)
                    else:
                        cursor.execute(sql_query)

                    results = cursor.fetchall()
                    columns = [desc.name for desc in cursor.description] if cursor.description else []
                    execution_time = time.time() - start_time

                    return DatabaseExecutionResult(
                        success=True,
                        results=[dict(row) for row in results],
                        row_count=len(results),
                        columns=columns,
                        execution_time=execution_time
                    )

        except psycopg2.Error as e:
            execution_time = time.time() - start_time
            return DatabaseExecutionResult(
                success=False,
                error=f"PostgreSQL error: {str(e)}",
                results=None,
                row_count=0,
                execution_time=execution_time
            )
        finally:
            if conn:
                conn.close()

    async def _execute_mysql(self, sql_query: str, params: Optional[List] = None) -> DatabaseExecutionResult:
        """Execute query on MySQL database"""
        try:
            import mysql.connector
        except ImportError:
            logger.error("mysql-connector-python not installed. Install with: pip install mysql-connector-python")
            return DatabaseExecutionResult(
                success=False,
                error='MySQL driver not installed',
                results=None,
                row_count=0,
                execution_time=0
            )

        start_time = time.time()
        conn = None

        try:
            conn = mysql.connector.connect(
                host=self.config['host'],
                port=self.config['port'],
                database=self.config['database'],
                user=self.config['user'],
                password=self.config['password'],
                connection_timeout=30,
                autocommit=True
            )

            cursor = conn.cursor(dictionary=True, buffered=True)

            if params:
                cursor.execute(sql_query, params)
            else:
                cursor.execute(sql_query)

            results = cursor.fetchall()
            columns = cursor.column_names if cursor.column_names else []
            execution_time = time.time() - start_time

            return DatabaseExecutionResult(
                success=True,
                results=results,
                row_count=len(results),
                columns=list(columns),
                execution_time=execution_time
            )

        except mysql.connector.Error as e:
            execution_time = time.time() - start_time
            return DatabaseExecutionResult(
                success=False,
                error=f"MySQL error: {str(e)}",
                results=None,
                row_count=0,
                execution_time=execution_time
            )
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    async def _execute_sqlite(self, sql_query: str, params: Optional[List] = None) -> DatabaseExecutionResult:
        """Execute query on SQLite database"""
        import sqlite3

        start_time = time.time()
        conn = None

        try:
            db_path = self.config.get('database', 'lab.db')
            conn = sqlite3.connect(db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row

            cursor = conn.cursor()

            if params:
                cursor.execute(sql_query, params)
            else:
                cursor.execute(sql_query)

            results = cursor.fetchall()
            columns = [description[0] for description in cursor.description] if cursor.description else []
            execution_time = time.time() - start_time

            return DatabaseExecutionResult(
                success=True,
                results=[dict(row) for row in results],
                row_count=len(results),
                columns=columns,
                execution_time=execution_time
            )

        except sqlite3.Error as e:
            execution_time = time.time() - start_time
            return DatabaseExecutionResult(
                success=False,
                error=f"SQLite error: {str(e)}",
                results=None,
                row_count=0,
                execution_time=execution_time
            )
        finally:
            if conn:
                conn.close()

    async def _execute_sqlserver(self, sql_query: str, params: Optional[List] = None) -> DatabaseExecutionResult:
        """Execute query on SQL Server database"""
        try:
            import pyodbc
        except ImportError:
            logger.error("pyodbc not installed. Install with: pip install pyodbc")
            return DatabaseExecutionResult(
                success=False,
                error='SQL Server driver not installed',
                results=None,
                row_count=0,
                execution_time=0
            )

        start_time = time.time()
        conn = None

        try:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={self.config['host']},{self.config['port']};"
                f"DATABASE={self.config['database']};"
                f"UID={self.config['user']};"
                f"PWD={self.config['password']};"
                f"Timeout=30;"
            )

            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()

            if params:
                cursor.execute(sql_query, params)
            else:
                cursor.execute(sql_query)

            results = []
            columns = [column[0] for column in cursor.description] if cursor.description else []

            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))

            execution_time = time.time() - start_time

            return DatabaseExecutionResult(
                success=True,
                results=results,
                row_count=len(results),
                columns=columns,
                execution_time=execution_time
            )

        except pyodbc.Error as e:
            execution_time = time.time() - start_time
            return DatabaseExecutionResult(
                success=False,
                error=f"SQL Server error: {str(e)}",
                results=None,
                row_count=0,
                execution_time=execution_time
            )
        finally:
            if conn:
                conn.close()


class QueryCache:
    """Simple in-memory cache for query results"""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache = {}
        self._timestamps = {}
        self._hits = 0
        self._misses = 0
        self._total_requests = 0

    def _generate_key(self, sql_query: str, params: Optional[List] = None) -> str:
        """Generate cache key for query"""
        query_hash = hashlib.md5(sql_query.encode()).hexdigest()
        if params:
            params_hash = hashlib.md5(str(params).encode()).hexdigest()
            return f"{query_hash}_{params_hash}"
        return query_hash

    def get(self, sql_query: str, params: Optional[List] = None) -> Optional[DatabaseExecutionResult]:
        """Get cached result if available and not expired"""
        self._total_requests += 1
        key = self._generate_key(sql_query, params)

        if key in self._cache:
            if time.time() - self._timestamps[key] < self.ttl_seconds:
                self._hits += 1
                logger.info(f"Cache hit for query: {sql_query[:50]}...")
                return self._cache[key]
            else:
                # Expired, remove from cache
                del self._cache[key]
                del self._timestamps[key]

        self._misses += 1
        return None

    def set(self, sql_query: str, result: DatabaseExecutionResult, params: Optional[List] = None):
        """Cache query result"""
        key = self._generate_key(sql_query, params)

        # Evict oldest entries if cache is full
        if len(self._cache) >= self.max_size:
            oldest_key = min(self._timestamps.keys(), key=lambda k: self._timestamps[k])
            del self._cache[oldest_key]
            del self._timestamps[oldest_key]

        self._cache[key] = result
        self._timestamps[key] = time.time()
        logger.info(f"Cached result for query: {sql_query[:50]}...")

    def clear(self):
        """Clear all cached results"""
        self._cache.clear()
        self._timestamps.clear()
        logger.info("Query cache cleared")

    def get_stats(self) -> CacheStats:
        """Get cache statistics"""
        hit_rate = (self._hits / self._total_requests * 100) if self._total_requests > 0 else 0

        return CacheStats(
            size=len(self._cache),
            max_size=self.max_size,
            hit_rate=hit_rate,
            total_requests=self._total_requests,
            hits=self._hits,
            misses=self._misses
        )