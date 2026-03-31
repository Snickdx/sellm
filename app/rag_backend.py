"""
Minimal RAG implementation for Requirements Chatbot
"""
# Apply pytree compatibility fix before importing sentence_transformers
try:
    from app import fix_pytree  # noqa: F401
except ImportError:
    pass

import warnings

# huggingface_hub: resume_download deprecation (pulled in via sentence-transformers)
warnings.filterwarnings(
    "ignore",
    message=r".*resume_download.*",
    category=FutureWarning,
    module=r"huggingface_hub\.file_download",
)

import pandas as pd
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import os
from typing import List, Dict
import json
import random

class RequirementsRAG:
    def __init__(self, excel_file: str, persist_directory: str = "./chroma_db_v2"):
        self.excel_file = excel_file
        self.persist_directory = persist_directory
        
        # Initialize embedding model
        print("Loading embedding model...")
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Initialize ChromaDB
        print("Initializing vector database...")
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False),
        )
        
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
    
    def _extract_natural_content(self, result: Dict) -> Dict:
        """Extract content from result in a natural, human-readable format"""
        document = result['document']
        metadata = result['metadata']
        
        # Parse the document to extract key information
        lines = document.split('\n')[1:]  # Skip "Sheet: X" line
        
        content = {}
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                
                if not value or value.lower() in ['nan', 'none', '']:
                    continue
                
                # Store important fields
                if key.lower() in ['id', 'name', 'title', 'description', 'role', 'type', 
                                   'stakeholder', 'client', 'goal', 'feature', 'requirement']:
                    content[key.lower()] = value
        
        return content
    
    def _add_verb_if_needed(self, text: str, context: str = 'feature') -> str:
        """Add appropriate verb to make text a complete sentence"""
        text_lower = text.lower().strip()
        
        # Remove trailing periods
        text_lower = text_lower.rstrip('.')
        
        # Check if it already starts with a verb (common verbs for features/requirements)
        verb_starters = ['handle', 'support', 'provide', 'allow', 'enable', 'process', 
                        'manage', 'generate', 'create', 'integrate', 'calculate', 'track',
                        'store', 'retrieve', 'display', 'export', 'import', 'validate',
                        'be able to', 'can', 'must', 'should', 'will']
        
        # If it already starts with a verb, return as is
        for verb in verb_starters:
            if text_lower.startswith(verb):
                return text
        
        # Check if it already has a verb phrase
        if any(phrase in text_lower for phrase in [' to ', ' be ', ' have ', ' do ', ' make ', ' can ', ' will ']):
            return text
        
        # Check if it's a noun phrase that needs a verb
        if context == 'feature':
            # For features, add appropriate verbs based on content
            if 'integration' in text_lower or 'integrate' in text_lower:
                # Extract what needs to be integrated
                rest = text_lower.replace('integration', '').replace('integrated', '').replace('integrate', '').strip()
                rest = rest.replace('with', '').strip()
                if rest:
                    return f"integrate with {rest}"
                else:
                    return "integrate with other systems"
            elif any(word in text_lower for word in ['customizable', 'custom', 'configurable']):
                # Extract the noun after customizable
                rest = text_lower.replace('customizable', '').replace('custom', '').replace('configurable', '').strip()
                if rest:
                    return f"have customizable {rest}"
                else:
                    return "have customizable options"
            elif any(word in text_lower for word in ['payroll', 'payment', 'billing']):
                if 'payroll' in text_lower:
                    # Check if it mentions frequency
                    if any(freq in text_lower for freq in ['weekly', 'monthly', 'biweekly', 'daily']):
                        return f"process {text_lower}"
                    else:
                        return f"handle {text_lower}"
                return f"handle {text_lower}"
            elif any(word in text_lower for word in ['report', 'reporting', 'reports']):
                return f"generate {text_lower}"
            elif any(word in text_lower for word in ['data', 'information', 'records', 'database']):
                return f"manage {text_lower}"
            elif any(word in text_lower for word in ['user', 'users', 'employee', 'employees']):
                return f"manage {text_lower}"
            else:
                # Default: add "support" for features
                return f"support {text_lower}"
        
        elif context == 'goal':
            # Goals might already be complete or need "to" + verb
            if not any(word in text_lower for word in [' to ', ' be ', ' have ', ' do ', ' make ', ' can ', ' will ']):
                # If it doesn't have a verb, add appropriate verb based on content
                if any(word in text_lower for word in ['cost', 'costs', 'budget', 'money', 'expense']):
                    return f"to reduce {text_lower}"
                elif any(word in text_lower for word in ['change', 'changes', 'update', 'updates']):
                    return f"to handle {text_lower}"
                elif any(word in text_lower for word in ['backup', 'recovery', 'resilience']):
                    return f"to ensure {text_lower}"
                else:
                    return f"to {text_lower}"
            return text
        
        return text

    def _extract_employee_subgroups(self, extracted_info: List[Dict]) -> List[str]:
        """Extract likely employee subgroup labels from retrieved structured fields."""
        subgroup_terms = []
        generic_terms = {"employee", "employees", "employer", "staff", "people", "person"}

        def add_term(raw: str):
            term = raw.strip().lower().replace("_", " ")
            if not term:
                return
            # Skip single generic tokens.
            if term in generic_terms:
                return
            # Keep compact natural labels.
            if len(term) <= 2 or len(term) > 50:
                return
            if term not in subgroup_terms:
                subgroup_terms.append(term)

        for info in extracted_info:
            for key in ["role", "type", "title", "name", "description"]:
                value = info.get(key, "")
                if not value:
                    continue
                text = str(value).lower()
                # Pull likely subgroup clues from common separators.
                for piece in text.replace(" and ", ",").replace("/", ",").split(","):
                    piece = piece.strip(" .;:-")
                    if not piece:
                        continue
                    # Keep role/category-like fragments.
                    if any(
                        marker in piece
                        for marker in [
                            "department",
                            "payroll",
                            "manager",
                            "lead",
                            "admin",
                            "finance",
                            "hr",
                            "tax",
                            "piecework",
                            "weekly",
                            "monthly",
                            "contract",
                            "full-time",
                            "part-time",
                        ]
                    ):
                        add_term(piece)

        return subgroup_terms[:5]
    
    def _generate_informal_response(self, results: List[Dict], query: str) -> str:
        """Generate a human-like, informal response as a non-technical stakeholder"""
        query_lower = query.lower()
        
        if not results:
            # Casual, human-like "I don't know" response
            responses = [
                "Hmm, I'm not sure about that. Can you ask me something else?",
                "I don't really know much about that. What else would you like to know?",
                "That's not something I'm familiar with. Maybe try asking about something else?",
                "I'm not sure I can help with that. Is there something else you'd like to ask?"
            ]
            return random.choice(responses)
        
        # Extract natural content from results
        extracted_info = []
        for result in results[:3]:  # Limit to top 3 for natural conversation
            info = self._extract_natural_content(result)
            if info:
                extracted_info.append(info)
        
        if not extracted_info:
            return "I'm not really sure how to answer that. Can you rephrase your question?"
        
        # Generate natural, informal response based on query type
        response_parts = []
        # Detect what they're asking about
        if any(w in query_lower for w in ['stakeholder', 'stakeholders', 'people', 'who', 'person']):
            response_parts.append("Oh, well, there are a few people involved in this project. ")
            if len(extracted_info) > 1:
                response_parts.append("Let me think... ")
            seen_people = set()
            added_count = 0
            for info in extracted_info:
                name = info.get('name', info.get('stakeholder', 'Someone'))
                role = info.get('role', info.get('type', ''))
                desc = info.get('description', '')
                person_key = f"{name}|{role}".strip().lower()
                if person_key in seen_people:
                    continue
                seen_people.add(person_key)
                
                if added_count == 0:
                    if role:
                        response_parts.append(f"There's {name}, who's the {role}. ")
                    else:
                        response_parts.append(f"There's {name}. ")
                else:
                    if role:
                        response_parts.append(f"And then there's {name}, they're the {role}. ")
                    else:
                        response_parts.append(f"Also {name}. ")
                
                if desc and len(desc) < 100:
                    response_parts.append(f"{desc} ")
                added_count += 1
        
        elif any(w in query_lower for w in ['goal', 'goals', 'objective', 'objectives', 'want', 'need']):
            response_parts.append("So, what we're really trying to do here is ")
            
            for i, info in enumerate(extracted_info):
                goal = info.get('goal', info.get('description', info.get('name', '')))
                if goal:
                    # Ensure the goal is properly formatted
                    goal_text = self._add_verb_if_needed(goal, context='goal')
                    
                    if i == 0:
                        response_parts.append(f"{goal_text.lower()}. ")
                    else:
                        response_parts.append(f"We also need {goal_text.lower()}. ")
        
        elif any(w in query_lower for w in ['feature', 'features', 'function', 'functionality', 'do', 'can']):
            response_parts.append("Well, the system should be able to ")
            
            for i, info in enumerate(extracted_info):
                feature = info.get('feature', info.get('name', info.get('description', '')))
                if feature:
                    # Ensure the feature has a proper verb
                    feature_text = self._add_verb_if_needed(feature, context='feature')
                    feature_text_lower = feature_text.lower().strip()
                    
                    # Check if feature_text already starts with a verb (so we don't duplicate "be able to")
                    verb_starters = ['handle', 'support', 'provide', 'allow', 'enable', 'process', 
                                    'manage', 'generate', 'create', 'integrate', 'calculate', 'track',
                                    'store', 'retrieve', 'display', 'export', 'import', 'validate',
                                    'have', 'do', 'make']
                    
                    starts_with_verb = any(feature_text_lower.startswith(verb) for verb in verb_starters)
                    
                    if i == 0:
                        if starts_with_verb:
                            response_parts.append(f"{feature_text_lower}. ")
                        else:
                            response_parts.append(f"{feature_text_lower}. ")
                    else:
                        if starts_with_verb:
                            response_parts.append(f"It should also {feature_text_lower}. ")
                        else:
                            response_parts.append(f"It should also be able to {feature_text_lower}. ")
        
        elif any(w in query_lower for w in ['budget', 'cost', 'costs', 'money', 'price', 'expensive']):
            response_parts.append("Money-wise, ")
            
            for i, info in enumerate(extracted_info):
                budget_info = info.get('budget', info.get('cost', info.get('description', '')))
                if budget_info:
                    # Ensure budget info is a complete thought
                    budget_text = budget_info.lower().strip()
                    if not budget_text.startswith(('we', 'it', 'the', 'our', 'i')):
                        budget_text = f"we're looking at {budget_text}"
                    response_parts.append(f"{budget_text}. ")
        
        elif any(w in query_lower for w in ['risk', 'risks', 'problem', 'problems', 'issue', 'concern', 'worry']):
            response_parts.append("Yeah, there are a few things we're worried about. ")
            
            for i, info in enumerate(extracted_info):
                risk = info.get('risk', info.get('description', info.get('name', '')))
                if risk:
                    risk_text = risk.lower().strip()
                    # Ensure it's a complete thought
                    if not risk_text.startswith(('we', 'it', 'the', 'our', 'there', 'that')):
                        risk_text = f"we're concerned about {risk_text}"
                    
                    if i == 0:
                        response_parts.append(f"{risk_text}. ")
                    else:
                        response_parts.append(f"Also, {risk_text}. ")
        
        else:
            # Generic response
            response_parts.append("So, ")
            seen_desc = set()
            for i, info in enumerate(extracted_info):
                desc = info.get('description', info.get('name', ''))
                if desc:
                    desc_text = desc.lower().strip()
                    if desc_text in seen_desc:
                        continue
                    seen_desc.add(desc_text)
                    # Ensure it's a complete sentence
                    if not desc_text.startswith(('we', 'it', 'the', 'our', 'this', 'that', 'i')):
                        desc_text = f"it's about {desc_text}"
                    
                    if i == 0:
                        response_parts.append(f"{desc_text}. ")
                    else:
                        response_parts.append(f"Also, {desc_text}. ")
        
        # Add a casual follow-up
        follow_ups = [
            "Does that make sense?",
            "Is that what you were looking for?",
            "Does that help?",
            "What else do you want to know?",
            "Anything else you're curious about?",
            "Hope that helps!",
        ]
        response_parts.append(random.choice(follow_ups))
        
        return "".join(response_parts)
    
    def generate_response(self, query: str) -> str:
        """Generate human-like, informal response as a non-technical stakeholder"""
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
        
        # Generate informal, human-like response
        response = self._generate_informal_response(results, query)
        
        return response


if __name__ == "__main__":
    # Test the RAG system
    rag = RequirementsRAG("data.xlsx")
    
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
