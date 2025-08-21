# Lab Text-to-SQL RAG System

A sophisticated RAG (Retrieval Augmented Generation) system that converts natural language questions about lab operations into SQL queries and executes them against your lab database.

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Natural       │    │   Vector Store  │    │   Lab Database  │
│   Language      │───▶│   (Qdrant)      │───▶│   (Your DB)     │
│   Question      │    │   Schema Search │    │   Query Exec    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   LLM (Ollama)  │
                    │   SQL Generation│
                    └─────────────────┘
```

## 📁 Project Structure

```
lab-rag-system/
├── docker-compose.yml          # Docker services configuration
├── .env                        # Environment variables
├── README.md                   # This file
├── api/                        # FastAPI application
│   ├── main.py                 # Main application entry point
│   ├── config.py               # Configuration settings
│   ├── models.py               # Pydantic models
│   ├── database.py             # Database connection manager
│   ├── vector_store.py         # Qdrant vector store operations
│   ├── sql_generator.py        # SQL generation with Ollama
│   ├── schema_processor.py     # Schema processing and ingestion
│   ├── requirements.txt        # Python dependencies
│   └── Dockerfile              # API container configuration
├── kb/                         # Knowledge base (your table schemas)
│   ├── catalog_index.jsonl     # Full table catalog
│   ├── o.json                  # POC table schemas
│   ├── r.json
│   ├── sa.json
│   ├── rr.json
│   ├── ep.json
│   ├── tat.json
│   ├── c.json
│   ├── cti.json
│   ├── m.json
│   ├── i.json
│   ├── mc.json
│   ├── mac.json
│   ├── ao.json
│   ├── ar.json
│   ├── asa.json
│   ├── arr.json
│   └── aep.json
└── logs/                       # Application logs
```

## 🚀 Quick Start

### 1. Clone and Setup

```bash
git clone <your-repo>
cd lab-rag-system
```

### 2. Configure Environment

Copy and edit the environment file:
```bash
cp .env.example .env
# Edit .env with your database credentials
```

### 3. Prepare Knowledge Base

Create your table schema files in the `kb/` directory. Each file should contain:

```json
{
  "table_name": "experiments",
  "description": "Laboratory experiments tracking",
  "columns": [
    {
      "name": "experiment_id",
      "type": "INTEGER",
      "description": "Unique experiment identifier",
      "primary_key": true
    },
    {
      "name": "title",
      "type": "VARCHAR(255)",
      "description": "Experiment title"
    },
    {
      "name": "status",
      "type": "VARCHAR(50)",
      "description": "Current status: pending, running, completed, failed"
    },
    {
      "name": "created_at",
      "type": "TIMESTAMP",
      "description": "Experiment creation timestamp"
    }
  ],
  "relationships": [
    "FOREIGN KEY (researcher_id) REFERENCES researchers(id)"
  ],
  "rows": [
    [1, "Protein Analysis", "completed", "2024-01-15T10:30:00"],
    [2, "Cell Culture Study", "running", "2024-01-16T09:15:00"]
  ]
}
```

### 4. Configure Database Driver

Uncomment the appropriate database driver in `api/requirements.txt`:

```bash
# For PostgreSQL
psycopg2-binary==2.9.7

# For MySQL  
mysql-connector-python==8.1.0

# For SQL Server
pyodbc==4.0.39
```

### 5. Start Services

```bash
docker-compose up -d
```

Monitor the startup process:
```bash
docker-compose logs -f
```

### 6. Wait for Model Downloads

First startup takes time as Ollama downloads AI models:
```bash
docker-compose logs -f ollama
```

### 7. Ingest Schema

Once all services are healthy:
```bash
curl -X POST http://localhost:8000/ingest/schema
```

### 8. Test the System

```bash
# Generate SQL without execution
curl -X POST http://localhost:8000/query/sql \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Show me all experiments completed this week",
    "execute_query": false
  }'

# Generate and execute SQL
curl -X POST http://localhost:8000/query/sql \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How many samples were processed today?",
    "execute_query": true,
    "limit": 10
  }'
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LAB_DB_HOST` | Lab database hostname | `localhost` |
| `LAB_DB_PORT` | Lab database port | `5432` |
| `LAB_DB_NAME` | Lab database name | `lab_db` |
| `LAB_DB_USER` | Database username | `lab_user` |
| `LAB_DB_PASSWORD` | Database password | `lab_password` |
| `LAB_DB_DRIVER` | Database driver | `postgresql` |
| `EMBEDDING_MODEL` | Ollama embedding model | `nomic-embed-text` |
| `CHAT_MODEL` | Ollama chat model | `llama3.2` |

### POC Tables

The system currently supports these 17 tables:
- `o` (Orders)
- `r` (Results)  
- `sa` (Sample Analysis)
- `rr` (Result Reviews)
- `ep` (Experiment Protocols)
- `tat` (Turnaround Time)
- `c` (Customers/Clients)
- `cti` (Customer Test Information)
- `m` (Materials/Methods)
- `i` (Instruments)
- `mc` (Material Consumption)
- `mac` (Machine/Equipment)
- `ao` (Analysis Orders)
- `ar` (Analysis Results)
- `asa` (Analysis Sample Assignment)
- `arr` (Analysis Result Reviews)
- `aep` (Analysis Experiment Protocols)

## 📚 API Endpoints

### Schema Management

- **POST** `/ingest/schema` - Ingest table schemas into vector store
- **GET** `/tables/available` - List available POC tables
- **GET** `/tables/schema/{table_name}` - Get specific table schema
- **DELETE** `/schema/reset` - Reset schema collection

### Query Generation

- **POST** `/query/sql` - Generate SQL from natural language
  ```json
  {
    "question": "Show me all pending experiments",
    "execute_query": true,
    "limit": 50
  }
  ```

### Monitoring

- **GET** `/health` - System health check
- **GET** `/cache/stats` - Query cache statistics
- **DELETE** `/cache/clear` - Clear query cache

## 🧠 Example Questions

The system understands various lab-related queries:

### Data Retrieval
- "Show me all experiments completed in the last 7 days"
- "What samples were processed yesterday?"
- "List all pending results waiting for approval"
- "Find experiments by researcher John Smith"

### Analytics
- "How many experiments failed this month?"
- "What's the average processing time for sample analysis?"
- "Which equipment has the highest usage rate?"
- "Show me the success rate by experiment type"

### Monitoring
- "Which samples are overdue for processing?"
- "What equipment needs maintenance?"
- "Show me all critical alerts from today"
- "List experiments that exceeded their scheduled time"

## 🛡️ Security Features

- **Read-only queries**: Only SELECT statements allowed
- **Query validation**: Blocks dangerous operations (DROP, DELETE, etc.)
- **Table restrictions**: Only POC tables accessible
- **Automatic limits**: Prevents large result sets
- **SQL injection protection**: Input validation and sanitization

## 🔍 Troubleshooting

### Common Issues

**Schema ingestion fails**
```bash
# Check if KB files exist
ls -la kb/

# Check API logs
docker-compose logs api
```

**Database connection fails**
```bash
# Test database connectivity
docker-compose exec api python -c "
from database import DatabaseManager
from config import settings
import asyncio

async def test():
    db = DatabaseManager(settings.DB_CONFIG)
    result = await db.test_connection()
    print(f'DB Connection: {result}')

asyncio.run(test())
"
```

**Models not downloading**
```bash
# Check Ollama logs
docker-compose logs ollama

# Manually pull models
docker-compose exec ollama ollama pull nomic-embed-text
docker-compose exec ollama ollama pull llama3.2
```

### Log Locations

- API logs: `logs/api.log`
- Docker logs: `docker-compose logs [service]`
- Qdrant logs: `docker-compose logs qdrant`
- Ollama logs: `docker-compose logs ollama`

## 📈 Performance Optimization

### For Large Datasets
- Implement connection pooling (see `database.py`)
- Enable query result caching
- Optimize vector search parameters
- Use more specific table schemas

### For High Volume
- Scale Qdrant with clustering
- Implement API rate limiting
- Add query result pagination
- Monitor resource usage

## 🚀 Production Deployment

### Security Checklist
- [ ] Use read-only database credentials
- [ ] Enable HTTPS/TLS
- [ ] Implement authentication
- [ ] Set up monitoring and alerting
- [ ] Configure backup strategies
- [ ] Review query logs regularly

### Scaling Considerations
- Use managed vector database service
- Implement API gateway for load balancing
- Add query analytics and monitoring
- Consider multi-region deployment

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## 📄 License

[Your License Here]

## 🆘 Support

For issues and questions:
- Check troubleshooting guide above
- Review API logs in `logs/` directory
- Open an issue with detailed error information