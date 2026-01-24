# Requirements Chatbot - RAG Implementation

A minimal RAG (Retrieval-Augmented Generation) chatbot for querying software requirements from an Excel document. This implementation uses open-source tools to provide an intelligent interface for exploring requirements documentation.

## Features

- **RAG System**: Uses ChromaDB for vector storage and sentence-transformers for embeddings
- **Intelligent Query Filtering**: Automatically detects query intent and filters results by sheet type
- **Web Chat UI**: Modern, responsive chat interface with HTML-formatted responses
- **FastAPI Backend**: Lightweight Python API server
- **Excel Integration**: Automatically loads requirements from multiple Excel sheets
- **Smart Result Formatting**: Properly formatted lists and structured responses

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

**Note**: The project includes a compatibility fix (`fix_pytree.py`) for torch/transformers version compatibility issues. This is automatically applied when importing the RAG backend.

## Usage

1. Make sure your Excel file `graph_model_nicholas (1).xlsx` is in the project directory.

2. Start the server:
```bash
python app.py
```

Or using uvicorn directly:
```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

3. Open your browser and navigate to:
```
http://localhost:8000
```

4. Start asking questions about your requirements!

## Architecture

### System Overview

The system follows a classic RAG (Retrieval-Augmented Generation) architecture with the following components:

```
┌─────────────┐
│   Browser   │
│  (Frontend) │
└──────┬──────┘
       │ HTTP/REST
       ▼
┌─────────────┐
│   FastAPI   │
│   Backend   │
└──────┬──────┘
       │
       ▼
┌─────────────┐      ┌──────────────┐
│  SimpleLLM  │─────▶│ Requirements │
│  (Response  │      │     RAG      │
│  Generator) │      └──────┬───────┘
└─────────────┘             │
                            ▼
                    ┌──────────────┐
                    │   ChromaDB   │
                    │  (Vector DB) │
                    └──────────────┘
```

### Components

1. **Frontend (`index.html`)**: Single-page web application with chat interface
2. **API Server (`app.py`)**: FastAPI server handling HTTP requests
3. **RAG Backend (`rag_backend.py`)**: Core RAG implementation with:
   - `RequirementsRAG`: Handles data loading, embedding, and retrieval
   - `SimpleLLM`: Generates responses from retrieved context
4. **Vector Database**: ChromaDB for persistent vector storage

## Data Processing & Chunking Strategy

### Chunking Approach

The system uses a **row-based chunking strategy** optimized for structured Excel data:

1. **Sheet Processing**: Each Excel sheet is processed independently
2. **Row-Level Chunks**: Each row becomes a single document chunk
3. **Text Representation**: All columns in a row are combined into a structured text format:
   ```
   Sheet: Stakeholder
   id: S1
   name: Product Manager
   role: Requirements Owner
   description: Responsible for defining product requirements
   ```

### Supported Sheets

The system processes the following sheet types:

- **People**: `Stakeholder`, `Client`, `Role`
- **Requirements**: `Requirement`, `Feature`, `FunctioFFnal_Requirement`
- **Planning**: `Goal`, `Timeline`, `Milestone`, `Task`
- **Constraints**: `Constraint`, `Risk`, `Qual_Scenario`
- **Budget**: `Budget`, `Line_Item`
- **Project**: `Project`

### Metadata Enrichment

Each chunk includes rich metadata for filtering and context:

- `sheet`: Source sheet name
- `row`: Original row index
- `sheet_type`: Categorized type (people, requirements, planning, etc.)
- `keywords`: Extracted keywords for better matching

## Embedding Strategy

### Model Selection

- **Model**: `all-MiniLM-L6-v2` from sentence-transformers
- **Dimensions**: 384-dimensional vectors
- **Why this model?**
  - Fast inference (~14,000 sentences/sec)
  - Good semantic understanding for technical documents
  - Balanced performance for structured data
  - Small model size (~80MB)

### Embedding Process

1. **Text Normalization**: Each row is converted to a structured text format
2. **Batch Encoding**: Documents are embedded in batches of 100 for efficiency
3. **Vector Storage**: Embeddings stored in ChromaDB with cosine similarity
4. **Persistence**: Vectors are persisted to disk for reuse across sessions

### Similarity Search

- **Distance Metric**: Cosine similarity (default for ChromaDB)
- **Search Space**: HNSW (Hierarchical Navigable Small World) index for fast approximate nearest neighbor search
- **Result Ranking**: Results sorted by distance (lower = more similar)

## Query Processing & Retrieval

### Query Intent Detection

The system uses keyword-based intent detection to identify what the user is asking about:

```python
intent_keywords = {
    'Stakeholder': ['stakeholder', 'stakeholders', 'people', 'person', 'who'],
    'Goal': ['goal', 'goals', 'objective', 'objectives'],
    'Feature': ['feature', 'features', 'functionality'],
    # ... etc
}
```

### Multi-Stage Filtering

1. **Pre-Filtering**: When intent is detected, search is restricted to relevant sheets
2. **Vector Search**: Semantic similarity search within filtered sheets
3. **Post-Filtering**: Additional filtering to remove irrelevant results
4. **Relevance Ranking**: Results sorted by similarity score

### Search Strategy

```python
# Example: Query "Who are the stakeholders?"
1. Detect intent → ['Stakeholder']
2. Filter search → Only search in Stakeholder sheet
3. Vector search → Find similar stakeholder entries
4. Post-filter → Remove any non-stakeholder results
5. Rank & return → Top N most relevant results
```

## Response Generation

### Template-Based Generation

Currently uses a template-based approach (can be extended with real LLMs):

1. **Context Retrieval**: Get top N relevant chunks
2. **Intent-Based Intro**: Generate contextual introduction based on query
3. **HTML Formatting**: Format results as structured HTML lists
4. **Field Extraction**: Prioritize key fields (id, name, description, etc.)

### Response Format

Responses are formatted as HTML for better readability:

```html
<strong>People - Stakeholder</strong>
<ul>
  <li><strong>id:</strong> S1 | <strong>name:</strong> Product Manager | role: Requirements Owner</li>
  <li><strong>id:</strong> S2 | <strong>name:</strong> Developer | role: Implementation</li>
</ul>
```

## Recent Improvements

### Query Accuracy Enhancements

- **Improved Sheet Detection**: Better keyword matching for query intent
- **Strict Filtering**: Results filtered by sheet type to prevent irrelevant responses
- **Post-Filtering**: Additional filtering layer to ensure only relevant results are shown
- **Sheet Type Categorization**: Automatic categorization of sheets for better filtering

### Response Formatting

- **HTML Lists**: Properly formatted HTML lists instead of plain text
- **Field Prioritization**: Key fields (id, name, description) shown prominently
- **Better Readability**: Improved spacing, styling, and structure
- **Frontend Rendering**: Frontend now renders HTML for rich formatting

## How It Works

### Initialization Flow

1. **Load Excel File**: Read all sheets using pandas/openpyxl
2. **Chunk Data**: Convert each row to a text document
3. **Generate Embeddings**: Create vector embeddings for all chunks
4. **Store in ChromaDB**: Persist vectors with metadata
5. **Ready for Queries**: System ready to answer questions

### Query Flow

1. **User Query**: User asks a question in the chat interface
2. **Intent Detection**: System detects what type of information is requested
3. **Filtered Search**: Search restricted to relevant sheets
4. **Vector Retrieval**: Find similar documents using cosine similarity
5. **Result Filtering**: Post-filter to ensure relevance
6. **Response Generation**: Format results as HTML
7. **Display**: Show formatted response in chat UI

## Customization

### Using a Real LLM

The current implementation uses a simple template-based response. To use a real LLM:

1. **Ollama** (recommended for local use):
```python
import requests

def generate_with_ollama(prompt):
    response = requests.post('http://localhost:11434/api/generate', json={
        'model': 'llama2',
        'prompt': prompt,
        'stream': False
    })
    return response.json()['response']
```

2. **HuggingFace Transformers**:
```python
from transformers import pipeline

generator = pipeline('text-generation', model='gpt2')
```

3. **OpenAI API** (requires API key):
```python
import openai

openai.api_key = "your-key"
response = openai.ChatCompletion.create(...)
```

### Adding More Sheets

Edit `rag_backend.py` and modify the `key_sheets` list in the `_load_requirements` method:

```python
key_sheets = [
    'Requirement', 'Feature', 'Stakeholder',
    # Add your sheet names here
]
```

### Changing the Embedding Model

To use a different embedding model:

```python
# In RequirementsRAG.__init__
self.embedding_model = SentenceTransformer('your-model-name')
```

Popular alternatives:
- `all-mpnet-base-v2`: Better quality, slower
- `paraphrase-MiniLM-L6-v2`: Similar to current, optimized for paraphrasing
- `multi-qa-MiniLM-L6-cos-v1`: Optimized for Q&A tasks

## Project Structure

```
.
├── app.py                 # FastAPI backend server
├── rag_backend.py         # RAG implementation
├── index.html            # Web chat UI
├── requirements.txt      # Python dependencies
├── fix_pytree.py         # Compatibility fix for torch
├── graph_model_nicholas (1).xlsx  # Requirements data
├── chroma_db_v2/         # Vector database (created automatically)
└── README.md             # This file
```

## Technologies Used

- **FastAPI**: Modern web framework for building APIs
- **ChromaDB**: Open-source vector database for embeddings
- **sentence-transformers**: Library for sentence embeddings
- **pandas**: Data manipulation and Excel file processing
- **openpyxl**: Excel file reading library
- **uvicorn**: ASGI server for FastAPI

## Performance Considerations

- **Embedding Speed**: ~14,000 sentences/sec with all-MiniLM-L6-v2
- **Search Speed**: Sub-millisecond with HNSW index
- **Batch Processing**: Documents processed in batches of 100
- **Persistence**: Database persists to disk, no re-indexing needed

## Limitations & Future Improvements

### Current Limitations

- Template-based response generation (no real LLM)
- Row-level chunking (no cross-row context)
- Keyword-based intent detection (could use ML classification)
- No conversation history (stateless queries)

### Potential Improvements

- Integrate real LLM (Ollama, OpenAI, etc.)
- Add conversation memory/context
- Implement re-ranking for better results
- Add support for multi-row chunks
- Implement query expansion
- Add confidence scores to responses
- Support for file uploads
- Multi-language support

## License

Open source - feel free to modify and use as needed.
