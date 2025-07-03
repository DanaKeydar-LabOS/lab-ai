# 🚀 Lab-AI API

A FastAPI-based backend application using modern Python tooling: Poetry for dependency management, `pytest` for testing, and `mypy` for static type checking.

## 📦 Project Setup & Usage

### 1. Install Poetry (if not installed)

```bash
pip install poetry


git clone https://github.com/your-org/lab-ai.git
cd lab-ai

# Use in-project virtual environment
poetry config virtualenvs.in-project true

# Install dependencies
poetry install

# Activate Shell & Run App
poetry shell
uvicorn app.main:app --reload
```

### 2. Project Structure
lab-ai/
├── app/              # Main application
│   ├── main.py       # FastAPI app entry
│   └── routers/      # API route modules (e.g. status.py)
├── tests/            # Unit/integration tests
├── .venv/            # Poetry-managed virtual environment
├── .gitignore
├── pyproject.toml    # Project config & dependencies
└── README.md

### 3. Run tests
```bash
poetry run pytest -v
```

### 4. Type Checking
```bash
poetry run mypy .
```

### 5. Environment Variables
Create a .env file in the root:
ENV=development
DEBUG=True

### 6. Common Commands
```bash
# Start the app
poetry run uvicorn app.main:app --reload

# Type check
poetry run mypy .

# Run tests
poetry run pytest
```
