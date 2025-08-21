import logging
import re
from typing import List, Dict, Any, Optional
import ollama
from config import settings
from models import QueryValidation, SQLGenerationResult

logger = logging.getLogger(__name__)


class SQLGenerator:
    """SQL query generator using Ollama LLM with enhanced query examples"""

    def __init__(self, ollama_host: str, ollama_port: int, embedding_model: str, chat_model: str):
        self.ollama_host = ollama_host
        self.ollama_port = ollama_port
        self.embedding_model = embedding_model
        self.chat_model = chat_model
        self.client = None

    async def initialize(self):
        """Initialize Ollama client and ensure models are available"""
        try:
            self.client = ollama.AsyncClient(host=f'http://{self.ollama_host}:{self.ollama_port}')
            logger.info(f"Connected to Ollama at {self.ollama_host}:{self.ollama_port}")

            # Ensure models are available
            await self._ensure_model_available(self.embedding_model)
            await self._ensure_model_available(self.chat_model)

        except Exception as e:
            logger.error(f"Failed to initialize Ollama client: {e}")
            raise

    async def _ensure_model_available(self, model_name: str):
        """Ensure the specified model is available in Ollama"""
        try:
            models_list = await self.client.list()
            available_models = [model['name'] for model in models_list.get('models', [])]

            if model_name not in available_models:
                logger.info(f"Pulling model {model_name}...")
                await self.client.pull(model_name)
                logger.info(f"Model {model_name} pulled successfully")
            else:
                logger.info(f"Model {model_name} is already available")

        except Exception as e:
            logger.error(f"Error ensuring model {model_name}: {e}")
            raise

    async def get_embedding(self, text: str) -> List[float]:
        """Generate embedding for given text using Ollama"""
        try:
            response = await self.client.embeddings(
                model=self.embedding_model,
                prompt=text
            )
            return response['embedding']
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    async def generate_sql(self, question: str, relevant_tables: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate SQL query based on the question and relevant table schemas with examples"""
        try:
            # Prepare enhanced schema context with examples
            schema_context = ""
            table_names = []
            query_examples = []

            for table_info in relevant_tables:
                table_names.append(table_info['table_name'])
                schema_context += f"\n{table_info['schema_text']}\n" + "=" * 50 + "\n"

                # Extract query examples from table data
                table_data = table_info.get('table_data', {})
                if 'examples' in table_data:
                    for example in table_data['examples']:
                        query_examples.append({
                            'table': table_info['table_name'],
                            'query': example.get('query', ''),
                            'description': example.get('description', ''),
                            'parameters': example.get('parameters', {})
                        })

            # Create the enhanced prompt for SQL generation
            prompt = self._create_enhanced_sql_prompt(question, schema_context, table_names, query_examples)

            # Generate SQL using LLM
            response = await self.client.generate(
                model=self.chat_model,
                prompt=prompt,
                stream=False
            )

            response_text = response['response']

            # Parse the response
            sql_result = self._parse_sql_response(response_text)

            return sql_result

        except Exception as e:
            logger.error(f"Error generating SQL query: {e}")
            raise


    def _create_enhanced_sql_prompt(self, question: str, schema_context: str,
                                    table_names: List[str], query_examples: List[Dict[str, Any]]) -> str:
        """Create a true pattern learning prompt without giving away the answer"""

        from datetime import datetime, timedelta
        current_date = datetime.now()
        week_ago = current_date - timedelta(days=7)
        current_date_str = current_date.strftime("%Y%m%d")
        week_ago_str = week_ago.strftime("%Y%m%d")

        # Show 2-3 concrete examples
        examples_text = ""
        if query_examples:
            examples_text = "Here are real working queries from this database:\n\n"
            for i, example in enumerate(query_examples[:3], 1):
                examples_text += f"Example {i}:\n"
                examples_text += f"SQL: {example['query']}\n"
                examples_text += f"Purpose: {example['description']}\n\n"

        return f"""You are writing SQL for a lab database. Study these working examples:

    {examples_text}

    Notice the patterns:
    - Dates are integers like 20250820 (not strings or functions)
    - Always use (NOLOCK) hints
    - Field names: aodate, aoordno, aopatcode, etc.
    - Simple WHERE conditions

    Available tables: {table_names}
    Today's date: {current_date_str}
    One week ago: {week_ago_str}

    Question: "{question}"

    Write SQL that matches these patterns. Use the same style and field names as the examples.

    SQL_QUERY:
    [your sql here]

    EXPLANATION:
    [brief explanation]

    TABLES_USED:
    [tables used]"""

    def _parse_sql_response(self, response_text: str) -> Dict[str, Any]:
        """Parse the LLM response to extract SQL components with much more robust parsing"""
        sql_query = ""
        explanation = ""
        tables_used = []

        try:
            logger.debug(f"Parsing LLM response: {response_text[:500]}...")

            # Try to extract SQL from code blocks first
            code_block_match = re.search(r'```sql\s*(.*?)\s*```', response_text, re.DOTALL | re.IGNORECASE)
            if code_block_match:
                sql_query = code_block_match.group(1).strip()
                logger.debug("Found SQL in code block")

            # If no code block, try labeled sections
            if not sql_query:
                sql_patterns = [
                    r'SQL_QUERY:\s*(.*?)(?=\n\n|EXPLANATION:|TABLES_USED:|$)',
                    r'SQL:\s*(.*?)(?=\n\n|EXPLANATION:|TABLES_USED:|$)',
                    r'Query:\s*(.*?)(?=\n\n|EXPLANATION:|TABLES_USED:|$)'
                ]

                for pattern in sql_patterns:
                    sql_match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)
                    if sql_match:
                        sql_query = sql_match.group(1).strip()
                        logger.debug(f"Found SQL with pattern: {pattern[:20]}...")
                        break

            # Last resort: find any SELECT statement
            if not sql_query:
                select_match = re.search(r'(SELECT\s+.*?;)', response_text, re.DOTALL | re.IGNORECASE)
                if select_match:
                    sql_query = select_match.group(1).strip()
                    logger.debug("Found SQL using SELECT pattern fallback")

            # Clean up the SQL query
            if sql_query:
                sql_query = self._clean_sql_query(sql_query)
            else:
                logger.warning("No SQL query found in LLM response")

            # Extract explanation - simpler approach
            explanation_match = re.search(r'EXPLANATION:\s*(.*?)(?=TABLES_USED:|$)', response_text,
                                          re.DOTALL | re.IGNORECASE)
            if explanation_match:
                explanation = explanation_match.group(1).strip()
            else:
                # Try to find explanation text after the SQL
                exp_patterns = [
                    r'This query\s+(.*?)(?=\n\n|TABLES|$)',
                    r'The query\s+(.*?)(?=\n\n|TABLES|$)',
                    r'```\s*\n\n(.*?)(?=\n\n|TABLES|$)'
                ]
                for pattern in exp_patterns:
                    exp_match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)
                    if exp_match:
                        explanation = exp_match.group(1).strip()
                        break

            # Extract tables - much simpler
            tables_match = re.search(r'TABLES_USED:\s*([a-zA-Z, ]+)', response_text, re.IGNORECASE)
            if tables_match:
                tables_text = tables_match.group(1).strip()
                tables_used = [t.strip() for t in tables_text.split(',') if t.strip() and len(t.strip()) < 10]

            # If no tables found in response, extract from SQL
            if not tables_used and sql_query:
                tables_used = self._extract_table_names(sql_query)

            # Clean up explanation
            if explanation:
                # Remove asterisks and markdown
                explanation = re.sub(r'\*+', '', explanation)
                explanation = re.sub(r'`+', '', explanation)
                explanation = explanation.strip()

            logger.info(f"Successfully parsed - SQL: {len(sql_query)} chars, Tables: {tables_used}")

        except Exception as e:
            logger.error(f"Error parsing SQL response: {e}")
            logger.debug(f"Full response text: {response_text}")

        return {
            'sql_query': sql_query,
            'explanation': explanation,
            'tables_used': tables_used,
            'full_response': response_text
        }

    def _clean_sql_query(self, sql_query: str) -> str:
        """Clean and format the SQL query with improved cleaning"""
        # Remove markdown code blocks if present
        sql_query = re.sub(r'```sql\s*', '', sql_query, flags=re.IGNORECASE)
        sql_query = re.sub(r'```\s*', '', sql_query)

        # Remove common prefixes
        sql_query = re.sub(r'^(sql|query):\s*', '', sql_query, flags=re.IGNORECASE)

        # Clean up whitespace but preserve important line breaks
        lines = sql_query.split('\n')
        cleaned_lines = []
        for line in lines:
            cleaned_line = re.sub(r'\s+', ' ', line.strip())
            if cleaned_line:
                cleaned_lines.append(cleaned_line)

        sql_query = ' '.join(cleaned_lines)

        # Ensure semicolon at the end
        if sql_query and not sql_query.endswith(';'):
            sql_query += ';'

        return sql_query

    def validate_sql(self, sql_query: str) -> QueryValidation:
        """Validate the generated SQL query with enhanced checks"""
        validation_result = QueryValidation(
            is_valid=True,
            errors=[],
            warnings=[]
        )

        try:
            # Check for potentially dangerous operations
            dangerous_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'TRUNCATE', 'ALTER', 'CREATE']
            sql_upper = sql_query.upper()

            for keyword in dangerous_keywords:
                if keyword in sql_upper:
                    validation_result.is_valid = False
                    validation_result.errors.append(f"Potentially dangerous operation detected: {keyword}")

            # Check if query starts with SELECT
            if not sql_query.strip().upper().startswith('SELECT'):
                validation_result.is_valid = False
                validation_result.errors.append("Only SELECT queries are allowed")

            # Check for LIMIT clause (more flexible check)
            if not any(limit_word in sql_upper for limit_word in ['LIMIT', 'TOP']):
                validation_result.warnings.append(
                    "Query doesn't include LIMIT/TOP clause - this could return many rows")

            # Check if query uses only POC tables
            used_tables = self._extract_table_names(sql_query)
            invalid_tables = [table for table in used_tables if table not in settings.POC_TABLES]

            if invalid_tables:
                validation_result.is_valid = False
                validation_result.errors.append(f"Query uses unauthorized tables: {invalid_tables}")

            # Enhanced validation: Check for common SQL patterns
            if '(NOLOCK)' not in sql_query.upper():
                validation_result.warnings.append("Consider adding NOLOCK hints for better performance")

            # Check for proper date format patterns
            if 'DATE' in sql_upper and not any(pattern in sql_query for pattern in ['YYYYMMDD', 'BETWEEN', '=']):
                validation_result.warnings.append("Ensure date formats follow YYYYMMDD pattern (e.g., 20250820)")

            # Basic syntax checks
            if sql_query.count('(') != sql_query.count(')'):
                validation_result.warnings.append("Unbalanced parentheses detected")

            # Check for potential SQL injection patterns
            injection_patterns = [
                r";\s*DROP",
                r";\s*DELETE",
                r"--",
                r"/\*.*\*/",
                r"UNION.*SELECT",
                r"xp_cmdshell",
                r"sp_executesql"
            ]

            for pattern in injection_patterns:
                if re.search(pattern, sql_query, re.IGNORECASE):
                    validation_result.is_valid = False
                    validation_result.errors.append("Potential SQL injection pattern detected")
                    break

        except Exception as e:
            logger.error(f"Error validating SQL: {e}")
            validation_result.is_valid = False
            validation_result.errors.append(f"Validation error: {str(e)}")

        return validation_result

    def _extract_table_names(self, sql_query: str) -> List[str]:
        """Extract table names from SQL query with enhanced pattern matching"""
        # Enhanced regex to find table names after FROM and JOIN keywords
        table_pattern = r'(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        matches = re.findall(table_pattern, sql_query, re.IGNORECASE)

        # Remove (NOLOCK) hints and clean up
        cleaned_matches = []
        for match in matches:
            clean_match = match.replace('(NOLOCK)', '').strip()
            if clean_match and clean_match not in cleaned_matches:
                cleaned_matches.append(clean_match)

        return cleaned_matches

    async def health_check(self) -> bool:
        """Check if SQL generator is healthy"""
        try:
            if not self.client:
                return False

            # Try to list models
            models_list = await self.client.list()
            available_models = [model['name'] for model in models_list.get('models', [])]

            # Check if required models are available
            return (self.embedding_model in available_models and
                    self.chat_model in available_models)

        except Exception as e:
            logger.error(f"SQL generator health check failed: {e}")
            return False

    async def get_available_models(self) -> List[str]:
        """Get list of available models"""
        try:
            models_list = await self.client.list()
            return [model['name'] for model in models_list.get('models', [])]
        except Exception as e:
            logger.error(f"Error getting available models: {e}")
            return []