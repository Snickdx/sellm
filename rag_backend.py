"""
Minimal RAG implementation for Requirements Chatbot
"""
# Apply pytree compatibility fix before importing sentence_transformers
try:
    import fix_pytree
except ImportError:
    pass

import pandas as pd
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import os
from typing import List, Dict
import json

class RequirementsRAG:
    def __init__(self, excel_file: str, persist_directory: str = "./chroma_db_v2"):
        self.excel_file = excel_file
        self.persist_directory = persist_directory
        
        # Initialize embedding model
        print("Loading embedding model...")
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Initialize ChromaDB
        print("Initializing vector database...")
        self.client = chromadb.PersistentClient(path=persist_directory)
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="requirements",
            metadata={"hnsw:space": "cosine"}
        )
        
        # Load data if collection is empty
        if self.collection.count() == 0:
            print("Loading requirements from Excel...")
            self._load_requirements()
        else:
            print(f"Found {self.collection.count()} existing documents in database")
    
    def _load_requirements(self):
        """Load requirements from Excel file and create embeddings"""
        try:
            xls = pd.ExcelFile(self.excel_file, engine='openpyxl')
            
            documents = []
            metadatas = []
            ids = []
            
            # Process key sheets that contain requirements
            key_sheets = [
                'Requirement', 'Feature', 'FunctioFFnal_Requirement', 
                'Goal', 'Constraint', 'Qual_Scenario', 'Project',
                'Stakeholder', 'Client', 'Role', 'Risk', 'Budget', 
                'Line_Item', 'Timeline', 'Milestone', 'Task'
            ]
            
            doc_id = 0
            for sheet_name in xls.sheet_names:
                if sheet_name not in key_sheets:
                    continue
                    
                try:
                    df = pd.read_excel(self.excel_file, sheet_name=sheet_name, engine='openpyxl')
                    
                    # Convert all columns to string and combine into text
                    for idx, row in df.iterrows():
                        # Skip empty rows
                        if row.isna().all():
                            continue
                        
                        # Create a text representation of the row
                        text_parts = []
                        for col in df.columns:
                            if pd.notna(row[col]):
                                text_parts.append(f"{col}: {row[col]}")
                        
                        if text_parts:
                            text = f"Sheet: {sheet_name}\n" + "\n".join(text_parts)
                            documents.append(text)
                            metadatas.append({
                                "sheet": sheet_name, 
                                "row": int(idx),
                                "sheet_type": self._get_sheet_type(sheet_name),
                                "keywords": ",".join(self._extract_keywords(sheet_name, text_parts))
                            })
                            ids.append(f"{sheet_name}_{doc_id}")
                            doc_id += 1
                            
                except Exception as e:
                    print(f"Error processing sheet {sheet_name}: {e}")
                    continue
            
            if documents:
                # Generate embeddings
                print(f"Generating embeddings for {len(documents)} documents...")
                embeddings = self.embedding_model.encode(documents, show_progress_bar=True)
                
                # Add to ChromaDB in batches to avoid size limits
                batch_size = 100
                for i in range(0, len(documents), batch_size):
                    end_idx = min(i + batch_size, len(documents))
                    batch_docs = documents[i:end_idx]
                    batch_embeddings = embeddings[i:end_idx]
                    batch_metadatas = metadatas[i:end_idx]
                    batch_ids = ids[i:end_idx]
                    
                    self.collection.add(
                        embeddings=batch_embeddings.tolist(),
                        documents=batch_docs,
                        metadatas=batch_metadatas,
                        ids=batch_ids
                    )
                    print(f"Added batch {i//batch_size + 1}: {len(batch_docs)} documents")
                
                print(f"Successfully loaded {len(documents)} documents into vector database")
            else:
                print("No documents found to load")
                
        except Exception as e:
            print(f"Error loading requirements: {e}")
            raise
    
    def _get_sheet_type(self, sheet_name: str) -> str:
        """Categorize sheet type for better search"""
        sheet_types = {
            'people': ['Stakeholder', 'Client', 'Role'],
            'requirements': ['Requirement', 'FunctioFFnal_Requirement', 'Feature'],
            'planning': ['Goal', 'Timeline', 'Milestone', 'Task'],
            'constraints': ['Constraint', 'Risk', 'Qual_Scenario'],
            'budget': ['Budget', 'Line_Item'],
            'project': ['Project']
        }
        
        for type_name, sheets in sheet_types.items():
            if sheet_name in sheets:
                return type_name
        return 'other'
    
    def _extract_keywords(self, sheet_name: str, text_parts: List[str]) -> List[str]:
        """Extract keywords for better matching"""
        keywords = [sheet_name.lower()]
        
        # Add common variations
        keyword_map = {
            'Stakeholder': ['stakeholder', 'stakeholders', 'people', 'person', 'who'],
            'Client': ['client', 'clients', 'customer', 'customers'],
            'Role': ['role', 'roles', 'responsibility', 'responsibilities'],
            'Feature': ['feature', 'features', 'functionality', 'function'],
            'Requirement': ['requirement', 'requirements', 'req', 'reqs'],
            'Goal': ['goal', 'goals', 'objective', 'objectives'],
            'Budget': ['budget', 'cost', 'costs', 'money', 'price'],
            'Risk': ['risk', 'risks', 'problem', 'problems', 'issue'],
            'Timeline': ['timeline', 'schedule', 'time', 'when', 'date']
        }
        
        if sheet_name in keyword_map:
            keywords.extend(keyword_map[sheet_name])
        
        return keywords
    
    def search(self, query: str, n_results: int = 5, filter_by_sheet_type: bool = True) -> List[Dict]:
        """Search for relevant requirements with intelligent sheet matching"""
        query_lower = query.lower()
        
        # First, try to find sheet-specific matches
        sheet_hints = self._detect_sheet_intent(query_lower)
        
        if sheet_hints and filter_by_sheet_type:
            # Search with sheet filter - prioritize exact matches
            formatted_results = []
            for sheet_hint in sheet_hints:
                where_filter = {"sheet": {"$eq": sheet_hint}}
                
                # Generate query embedding
                query_embedding = self.embedding_model.encode([query]).tolist()[0]
                
                # Search in ChromaDB with filter - get more results to ensure we have enough
                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=max(n_results, 10),  # Get more to ensure quality
                    where=where_filter
                )
                
                # Format results
                if results['documents'] and len(results['documents'][0]) > 0:
                    for i in range(len(results['documents'][0])):
                        formatted_results.append({
                            'document': results['documents'][0][i],
                            'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                            'distance': results['distances'][0][i] if results['distances'] else None
                        })
            
            # Sort by relevance and return top results
            formatted_results.sort(key=lambda x: x['distance'] or 0)
            return formatted_results[:n_results]
        else:
            # Fallback to general search, but still filter by sheet type if detected
            query_embedding = self.embedding_model.encode([query]).tolist()[0]
            
            # If we detected sheet hints but filter_by_sheet_type is False, still use them for filtering
            where_filter = None
            if sheet_hints and filter_by_sheet_type:
                # Filter by sheet type category
                sheet_types = set()
                for sheet in sheet_hints:
                    sheet_type = self._get_sheet_type(sheet)
                    if sheet_type != 'other':
                        sheet_types.add(sheet_type)
                
                if sheet_types:
                    # Filter by sheet_type metadata
                    where_filter = {"sheet_type": {"$in": list(sheet_types)}}
            
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results * 2 if where_filter else n_results,  # Get more if filtering
                where=where_filter
            )
            
            # Format results
            formatted_results = []
            if results['documents'] and len(results['documents'][0]) > 0:
                for i in range(len(results['documents'][0])):
                    result_sheet = results['metadatas'][0][i].get('sheet', '') if results['metadatas'] else ''
                    # Additional filtering: if we have sheet hints, prioritize those sheets
                    if sheet_hints and filter_by_sheet_type:
                        if result_sheet not in sheet_hints:
                            # Check if it's in the same category
                            result_sheet_type = self._get_sheet_type(result_sheet)
                            expected_types = {self._get_sheet_type(s) for s in sheet_hints}
                            if result_sheet_type not in expected_types:
                                continue  # Skip results from wrong sheet types
                    
                    formatted_results.append({
                        'document': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                        'distance': results['distances'][0][i] if results['distances'] else None
                    })
            
            # Sort by relevance
            formatted_results.sort(key=lambda x: x['distance'] or 0)
            return formatted_results[:n_results]
    
    def _detect_sheet_intent(self, query: str) -> List[str]:
        """Detect which sheets the user is asking about with improved matching"""
        # Normalize query - split into words for better matching
        query_words = set(query.lower().split())
        
        intent_keywords = {
            'Stakeholder': ['stakeholder', 'stakeholders', 'people', 'person', 'who', 'whom'],
            'Client': ['client', 'clients', 'customer', 'customers'],
            'Role': ['role', 'roles', 'responsibility', 'responsibilities'],
            'Feature': ['feature', 'features', 'functionality'],
            'Requirement': ['requirement', 'requirements', 'req', 'reqs'],
            'FunctioFFnal_Requirement': ['functional requirement', 'functional'],
            'Goal': ['goal', 'goals', 'objective', 'objectives'],
            'Budget': ['budget', 'cost', 'costs', 'money', 'price', 'pricing'],
            'Risk': ['risk', 'risks', 'problem', 'problems', 'issue', 'issues'],
            'Timeline': ['timeline', 'schedule', 'time', 'when', 'date', 'deadline'],
            'Project': ['project', 'overview', 'description', 'about']
        }
        
        detected_sheets = []
        # Check for exact word matches first (higher priority)
        for sheet, keywords in intent_keywords.items():
            # Check if any keyword appears as a whole word in the query
            for keyword in keywords:
                # Check as whole word (with word boundaries)
                if keyword in query.lower():
                    if sheet not in detected_sheets:
                        detected_sheets.append(sheet)
                    break  # Found a match for this sheet, move to next
        
        return detected_sheets
    
    def _format_search_results(self, results: List[Dict], query: str, format_html: bool = True) -> str:
        """Format search results in a readable way with proper list formatting"""
        if not results:
            return "No relevant information found."
        
        # Group by sheet type
        by_sheet = {}
        for result in results:
            sheet = result['metadata'].get('sheet', 'Unknown')
            if sheet not in by_sheet:
                by_sheet[sheet] = []
            by_sheet[sheet].append(result)
        
        if format_html:
            # HTML formatting for better readability
            formatted_parts = []
            
            for sheet_name, sheet_results in by_sheet.items():
                sheet_type = self._get_sheet_type(sheet_name)
                
                # Create a nice header
                if sheet_type == 'people':
                    header = f"<strong>People - {sheet_name}</strong>"
                elif sheet_type == 'requirements':
                    header = f"<strong>Requirements - {sheet_name}</strong>"
                elif sheet_type == 'planning':
                    header = f"<strong>Planning - {sheet_name}</strong>"
                elif sheet_type == 'budget':
                    header = f"<strong>Budget - {sheet_name}</strong>"
                elif sheet_type == 'constraints':
                    header = f"<strong>Constraints - {sheet_name}</strong>"
                else:
                    header = f"<strong>{sheet_name}</strong>"
                
                formatted_parts.append(f"<div style='margin-top: 12px; margin-bottom: 8px;'>{header}</div>")
                formatted_parts.append("<ul style='margin: 0; padding-left: 20px;'>")
                
                # Format each result as a list item
                for result in sheet_results:
                    content = self._clean_document_content(result['document'])
                    # Content is already HTML formatted, so use it directly
                    formatted_parts.append(f"<li style='margin-bottom: 8px; line-height: 1.5;'>{content}</li>")
                
                formatted_parts.append("</ul>")
            
            return "\n".join(formatted_parts)
        else:
            # Plain text formatting (fallback)
            formatted_parts = []
            
            for sheet_name, sheet_results in by_sheet.items():
                sheet_type = self._get_sheet_type(sheet_name)
                
                # Create a nice header
                if sheet_type == 'people':
                    header = f"PEOPLE - {sheet_name}:"
                elif sheet_type == 'requirements':
                    header = f"REQUIREMENTS - {sheet_name}:"
                elif sheet_type == 'planning':
                    header = f"PLANNING - {sheet_name}:"
                elif sheet_type == 'budget':
                    header = f"BUDGET - {sheet_name}:"
                elif sheet_type == 'constraints':
                    header = f"CONSTRAINTS - {sheet_name}:"
                else:
                    header = f"{sheet_name}:"
                
                formatted_parts.append(header)
                
                # Format each result
                for i, result in enumerate(sheet_results, 1):
                    content = self._clean_document_content(result['document'])
                    formatted_parts.append(f"   {i}. {content}")
                
                formatted_parts.append("")  # Add spacing
            
            return "\n".join(formatted_parts)
    
    def _clean_document_content(self, document: str) -> str:
        """Clean and format document content for better readability"""
        lines = document.split('\n')[1:]  # Skip the "Sheet: X" line
        
        # Extract key fields for better display
        key_fields = {}
        other_fields = []
        
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                
                # Skip empty or redundant values
                if not value or value.lower() == 'nan' or value.lower() == 'none':
                    continue
                
                # Prioritize important fields
                key_lower = key.lower()
                if key_lower in ['id', 'name', 'description', 'title', 'role', 'type', 'stakeholder', 'client']:
                    key_fields[key] = value
                else:
                    other_fields.append((key, value))
        
        # Format: prioritize key fields, then show other important ones
        formatted_parts = []
        
        # Add key fields first
        for key in ['id', 'name', 'title', 'stakeholder', 'client', 'role', 'type', 'description']:
            if key in key_fields:
                formatted_parts.append(f"<strong>{key}:</strong> {key_fields[key]}")
        
        # Add a few other important fields (limit to avoid clutter)
        for key, value in other_fields[:3]:
            formatted_parts.append(f"{key}: {value}")
        
        return " | ".join(formatted_parts) if formatted_parts else document
    
    def get_context(self, query: str, n_results: int = 3) -> str:
        """Get context from relevant requirements for RAG"""
        results = self.search(query, n_results=n_results, filter_by_sheet_type=True)
        
        if not results:
            return "No relevant information found."
        
        return self._format_search_results(results, query, format_html=True)


# Simple LLM wrapper - using a template-based approach
# For production, you'd use Ollama, HuggingFace, or OpenAI
class SimpleLLM:
    def __init__(self, rag: RequirementsRAG):
        self.rag = rag
    
    def generate_response(self, query: str) -> str:
        """Generate response using RAG with improved filtering and formatting"""
        query_lower = query.lower()
        
        # Detect what the user is asking about
        detected_sheets = self.rag._detect_sheet_intent(query_lower)
        
        # Get relevant context with strict filtering
        results = self.rag.search(query, n_results=5, filter_by_sheet_type=True)
        
        # Post-filter: Remove results that don't match the query intent
        if detected_sheets:
            expected_sheet_types = {self.rag._get_sheet_type(sheet) for sheet in detected_sheets}
            filtered_results = []
            for result in results:
                result_sheet = result['metadata'].get('sheet', '')
                result_sheet_type = self.rag._get_sheet_type(result_sheet)
                # Keep if it matches the expected sheet or sheet type
                if result_sheet in detected_sheets or result_sheet_type in expected_sheet_types:
                    filtered_results.append(result)
            
            # If we filtered out too many, keep at least the top 2-3
            if len(filtered_results) < 2 and len(results) >= 2:
                filtered_results = results[:3]
            
            results = filtered_results
        
        if not results:
            return "I couldn't find any relevant information about that. Try asking about stakeholders, features, requirements, goals, budget, or project details."
        
        # Format the response based on what was found (use HTML formatting)
        formatted_context = self.rag._format_search_results(results, query, format_html=True)
        
        # Generate contextual intro based on detected intent
        if any(w in query_lower for w in ['stakeholder', 'stakeholders', 'people', 'who']):
            intro = "Based on the requirements documentation, here are the stakeholders:"
        elif any(w in query_lower for w in ['feature', 'features', 'function', 'functionality']):
            intro = "Based on the requirements documentation, here are the relevant features and functionality:"
        elif any(w in query_lower for w in ['requirement', 'requirements', 'req', 'reqs']):
            intro = "Based on the requirements documentation, here are the relevant requirements:"
        elif any(w in query_lower for w in ['goal', 'goals', 'objective', 'objectives']):
            intro = "Based on the requirements documentation, here are the relevant goals and objectives:"
        elif any(w in query_lower for w in ['budget', 'cost', 'costs', 'money', 'price']):
            intro = "Based on the requirements documentation, here's the budget and cost information:"
        elif any(w in query_lower for w in ['risk', 'risks', 'problem', 'problems']):
            intro = "Based on the requirements documentation, here are the risks and issues identified:"
        else:
            intro = "Based on the requirements documentation, here's what I found:"
        
        response = f"""{intro}

{formatted_context}

<p style='margin-top: 16px; color: #666; font-size: 14px;'>Is there anything specific you'd like to know more about?</p>"""
        
        return response


if __name__ == "__main__":
    # Test the RAG system
    rag = RequirementsRAG("graph_model_nicholas (1).xlsx")
    
    test_queries = [
        "What are the main features?",
        "What is the project about?",
        "What are the payroll requirements?"
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        results = rag.search(query, n_results=3)
        for i, result in enumerate(results, 1):
            print(f"\nResult {i}:")
            print(result['document'][:200] + "...")
