# Requirements Gathering Training System - RAG Implementation

A RAG-based training system that simulates a non-technical stakeholder for requirements gathering practice. The system uses an Excel-based knowledge source to role-play as a stakeholder, providing informal, human-like responses that trainees must extract, document, and formalize into proper requirements documentation.

## Purpose

This system is designed for **requirements gathering training**. It simulates a non-technical stakeholder who provides information in a casual, informal manner - just like in real-world requirements gathering sessions. 

**Training Objectives:**
- Practice asking effective questions to extract requirements
- Learn to identify key information from informal, unstructured conversations
- Develop skills in formalizing informal stakeholder input into structured requirements
- Practice identifying gaps and asking appropriate follow-up questions
- Experience the challenge of working with non-technical stakeholders

**Important**: The system does NOT reference the knowledge source directly. Responses are human-like and informal, as if speaking with a real non-technical stakeholder. Trainees must take notes during the conversation and then formalize the information into proper requirements documentation.

## Features

- **Stakeholder Simulation**: Role-plays as a non-technical stakeholder with natural, informal language
- **RAG System**: Uses ChromaDB for vector storage and sentence-transformers for embeddings
- **Intelligent Query Understanding**: Detects query intent and responds contextually
- **Web Chat UI**: Modern, responsive chat interface for natural conversation
- **FastAPI Backend**: Lightweight Python API server
- **Excel Knowledge Base**: Uses Excel sheets as the ground truth for stakeholder responses

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

**Note**: The project includes a compatibility fix (`fix_pytree.py`) for torch/transformers version compatibility issues. This is automatically applied when importing the RAG backend.

## Usage

1. Make sure your Excel file `graph_model_nicholas (1).xlsx` is in the project directory. This file contains the stakeholder knowledge base.

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

4. Start practicing requirements gathering! 
   - Ask questions as you would in a real stakeholder interview
   - Take notes during the conversation (outside the system)
   - After the session, formalize the informal responses into structured requirements documentation

### Training Tips

- **Ask open-ended questions**: "Tell me about..." or "What are your concerns about..."
- **Follow up on vague answers**: If the stakeholder says "it should be fast", ask "What does 'fast' mean to you?"
- **Identify gaps**: Notice when information is missing and ask clarifying questions
- **Take comprehensive notes**: You'll need to formalize everything after the conversation
- **Practice different question types**: Try asking about stakeholders, goals, features, constraints, risks, and budget

## Architecture

### System Overview

The system follows a RAG (Retrieval-Augmented Generation) architecture designed for role-playing:

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
│  (Stakeholder│      │     RAG      │
│  Simulator) │      └──────┬───────┘
└─────────────┘             │
                            ▼
                    ┌──────────────┐
                    │   ChromaDB   │
                    │  (Vector DB) │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  Excel File  │
                    │ (Knowledge   │
                    │    Base)     │
                    └──────────────┘
```

### Components

1. **Frontend (`index.html`)**: Single-page web application with chat interface
2. **API Server (`app.py`)**: FastAPI server handling HTTP requests
3. **RAG Backend (`rag_backend.py`)**: Core RAG implementation with:
   - `RequirementsRAG`: Handles data loading, embedding, and retrieval
   - `SimpleLLM`: Generates informal, human-like stakeholder responses
4. **Vector Database**: ChromaDB for persistent vector storage
5. **Knowledge Base**: Excel file containing stakeholder information (not directly referenced in responses)

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

The system processes the following sheet types from the Excel knowledge base:

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

The system uses keyword-based intent detection to understand what the trainee is asking:

```python
intent_keywords = {
    'Stakeholder': ['stakeholder', 'stakeholders', 'people', 'person', 'who'],
    'Goal': ['goal', 'goals', 'objective', 'objectives', 'want', 'need'],
    'Feature': ['feature', 'features', 'functionality', 'do', 'can'],
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

### Human-Like Stakeholder Simulation

The system generates informal, natural responses that mimic a non-technical stakeholder:

**Key Characteristics:**
- **Informal language**: Uses casual phrases like "Oh, well...", "Let me think...", "Yeah, there are..."
- **No technical jargon**: Avoids formal requirements terminology
- **Natural flow**: Responses feel conversational, not structured
- **Uncertainty**: Sometimes includes phrases like "I'm not sure" or "Does that make sense?"
- **No source references**: Never mentions sheets, documents, or technical sources

### Response Examples

**Query**: "Who are the stakeholders?"

**Response**: "Oh, well, there are a few people involved in this project. Let me think... There's Sarah, who's the Product Manager. And then there's John, they're the Lead Developer. Also Mike, he's our QA lead. Does that help?"

**Query**: "What are the main goals?"

**Response**: "So, what we're really trying to do here is... reduce operational costs. Also, we need to be able to handle changes in legislation quickly. And make sure we have good backup and recovery in place. Is that what you were looking for?"

### Response Formatting

- **No HTML lists**: Responses are plain text paragraphs
- **Natural language**: Uses conversational connectors
- **Casual follow-ups**: Ends with questions like "Does that make sense?" or "What else do you want to know?"

## Training Workflow

### For Trainees

**During the Conversation:**
1. **Start Conversation**: Begin with an introduction or open-ended question
2. **Ask Questions**: Use natural language to gather information - ask about stakeholders, goals, features, constraints, etc.
3. **Follow Up**: Ask clarifying questions based on responses to fill gaps
4. **Take Notes**: Document what you learn (outside the system) - the stakeholder speaks informally, so you need to capture and structure the information

**After the Conversation:**
5. **Formalize Requirements**: Convert the informal, unstructured responses into formal requirements documentation:
   - Identify stakeholders and their roles
   - Extract functional and non-functional requirements
   - Document goals and objectives
   - List constraints and risks
   - Structure everything into a proper requirements document format

**Key Challenge**: The stakeholder will speak casually and may not use technical terminology. Your job is to extract the essential information and formalize it.

### Example Training Session

**Conversation:**
```
Trainee: Hi, can you tell me about the project?
Stakeholder: Oh sure! So we're building this system to help manage our operations better. 
            We really need something that can handle changes quickly, especially with 
            regulations and stuff. Does that help?

Trainee: Who else is involved in this project?
Stakeholder: Let me think... There's Sarah, who's the Product Manager. And then there's 
            John, they're the Lead Developer. Also Mike, he's our QA lead. What else 
            do you want to know?

Trainee: What are your main concerns?
Stakeholder: Yeah, there are a few things we're worried about. The system needs to be 
            really reliable, especially if our local infrastructure isn't super stable. 
            Also, we need to keep costs down - hosting, staff, support, all that stuff. 
            Hope that helps!
```

**Trainee's Formalized Requirements (created after the conversation):**

```
STAKEHOLDERS:
- Sarah: Product Manager
- John: Lead Developer  
- Mike: QA Lead

GOALS:
- G1: Build a system to manage operations more effectively
- G2: System must handle changes quickly, particularly regulatory changes

NON-FUNCTIONAL REQUIREMENTS:
- NFR1: System must be highly reliable
- NFR2: System must function in unstable local infrastructure environments
- NFR3: Minimize operational costs (hosting, staff, support)

CONSTRAINTS:
- C1: Local infrastructure may be unstable
- C2: Budget constraints require cost minimization
```

**Note**: The trainee has extracted structured requirements from the informal conversation, identifying stakeholders, goals, non-functional requirements, and constraints.

## Customization

### Adjusting Response Style

To make responses more or less formal, edit the `_generate_informal_response` method in `rag_backend.py`:

```python
# More casual
response_parts.append("Yeah, so... ")

# More professional (but still informal)
response_parts.append("Well, from our perspective... ")
```

### Using a Real LLM (Recommended)

The system now supports real LLMs for much more natural, human-like responses. The template-based approach is limited - using a real LLM is the standard RAG approach.

#### Option 1: Ollama (Recommended - Free & Local)

**Ollama** is the easiest way to get high-quality, local LLM responses:

1. **Install Ollama**: Download from [ollama.ai](https://ollama.ai)

2. **Pull a model** (choose one):
   ```bash
   ollama pull llama3.2        # Fast, good quality (recommended)
   ollama pull mistral         # Alternative option
   ollama pull phi3            # Smaller, faster
   ```

3. **Start the server** (Ollama runs automatically):
   ```bash
   # Ollama should start automatically, or:
   ollama serve
   ```

4. **Run your app** (it will auto-detect Ollama):
   ```bash
   python app.py
   ```

   Or specify the model:
   ```bash
   LLM_MODEL=llama3.2 python app.py
   ```

**Benefits:**
- ✅ Free and runs locally (no API costs)
- ✅ Privacy (data stays on your machine)
- ✅ High-quality, natural responses
- ✅ Works offline

#### Option 2: OpenAI API

For cloud-based LLM (requires API key):

1. **Install OpenAI package**:
   ```bash
   pip install openai
   ```

2. **Set your API key**:
   ```bash
   export OPENAI_API_KEY="your-key-here"
   ```

3. **Run with OpenAI backend**:
   ```bash
   LLM_BACKEND=openai LLM_MODEL=gpt-3.5-turbo python app.py
   ```

#### Option 3: Template Fallback

If no LLM is available, the system automatically falls back to template-based generation:

```bash
LLM_BACKEND=template python app.py
```

**Note**: Template-based responses are limited in quality and naturalness. A real LLM is strongly recommended.

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
├── rag_backend.py         # RAG implementation (retrieval)
├── llm_wrapper.py        # LLM wrapper (Ollama/OpenAI/template)
├── index.html            # Web chat UI
├── requirements.txt      # Python dependencies
├── fix_pytree.py         # Compatibility fix for torch
├── graph_model_nicholas (1).xlsx  # Knowledge base (stakeholder information)
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

## Design Principles

### Why No Source References?

The system is designed for **training**, not document querying. The training objective is to practice:
- **Extracting information from conversation**: Real stakeholders don't provide structured documentation
- **Identifying important information**: Learning to distinguish key requirements from casual conversation
- **Formalizing requirements**: Converting informal input into structured, formal requirements documentation
- **Working without documentation**: In real scenarios, requirements often come from conversations, not documents

If the system showed source references, trainees would skip the critical skill of extracting and structuring information from informal conversation.

### Why Informal Language?

Real stakeholders are often non-technical and speak informally. The system simulates this to:
- **Provide realistic training scenarios**: Mimics actual stakeholder conversations
- **Challenge trainees**: Forces extraction of structured information from unstructured conversation
- **Prepare for real-world**: Most requirements gathering happens through informal conversations
- **Build critical skills**: Trainees learn to ask the right questions and formalize responses

The informal language is intentional - it's the core challenge that makes this effective training.

## LLM Integration

### Why Use a Real LLM?

The template-based approach has significant limitations:
- ❌ Poor grammar and awkward phrasing
- ❌ Limited natural language variation
- ❌ Can't handle complex queries well
- ❌ Feels robotic, not human-like

**Using a real LLM (like Ollama) provides:**
- ✅ Natural, human-like responses
- ✅ Proper grammar automatically
- ✅ Better context understanding
- ✅ More conversational and varied responses
- ✅ Handles edge cases better

### How RAG + LLM Works

1. **Retrieval**: System finds relevant context from Excel data using vector search
2. **Augmentation**: Context is formatted into a prompt for the LLM
3. **Generation**: LLM generates a natural, human-like response based on the context
4. **Persona**: LLM is instructed to respond as a non-technical stakeholder

This is the **standard RAG pattern** used in production systems.

### Recommended Setup

**For best results, use Ollama with llama3.2:**
```bash
# Install Ollama, then:
ollama pull llama3.2
python app.py  # Auto-detects Ollama
```

The system will automatically:
- Use Ollama if available
- Fall back to template if Ollama isn't running
- Provide much better responses with LLM

## Limitations & Future Improvements

### Current Limitations

- ~~Template-based response generation~~ ✅ **Fixed with LLM support**
- Row-level chunking (no cross-row context)
- Keyword-based intent detection (could use ML classification)
- No conversation history (stateless queries)
- Fixed response style (could vary by stakeholder personality)

### Potential Improvements

- ✅ ~~Integrate real LLM~~ **Done!** Use Ollama or OpenAI
- Add conversation memory/context for follow-up questions
- Implement multiple stakeholder personas with different communication styles
- Add support for multi-turn conversations with context
- Implement query expansion for better retrieval
- Add confidence scores (internal, not shown to user)
- Support for different training scenarios
- Multi-language support
- Fine-tune LLM prompts for better stakeholder persona

## License

Open source - feel free to modify and use as needed.
