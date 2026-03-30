"""
Hybrid Neo4j RAG Implementation
Combines vector search with graph relationships for better context retrieval
"""
# Apply pytree compatibility fix before importing sentence_transformers
try:
    import fix_pytree
except ImportError:
    pass

import pandas as pd
from sentence_transformers import SentenceTransformer
from typing import List, Dict
import numpy as np

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    print("⚠ neo4j package not installed. Install with: pip install neo4j")


class RequirementsRAGNeo4j:
    """
    Hybrid Neo4j RAG system combining:
    - Vector search for semantic similarity
    - Graph traversal for relationship-based queries
    """
    
    def __init__(self, excel_file: str,
                 neo4j_uri: str = "bolt://localhost:7687",
                 neo4j_user: str = "neo4j",
                 neo4j_password: str = "password"):
        """
        Initialize Neo4j RAG system
        
        Args:
            excel_file: Path to Excel file
            neo4j_uri: Neo4j connection URI
            neo4j_user: Neo4j username
            neo4j_password: Neo4j password
        """
        if not NEO4J_AVAILABLE:
            raise ImportError("neo4j package required. Install with: pip install neo4j")
        
        self.excel_file = excel_file
        
        # Initialize embedding model
        print("Loading embedding model...")
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        
        # Initialize Neo4j
        print("Connecting to Neo4j...")
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        
        # Test connection
        try:
            with self.driver.session() as session:
                result = session.run("RETURN 1 as test")
                result.single()
            print("✓ Neo4j connected successfully")
        except Exception as e:
            print(f"⚠ Neo4j connection failed: {e}")
            raise
        
        # Load data if database is empty
        node_count = self._count_nodes()
        if node_count == 0:
            print("Loading requirements from Excel into Neo4j...")
            self._load_requirements()
        else:
            print(f"Found {node_count} existing nodes in Neo4j")
    
    def _count_nodes(self) -> int:
        """Count nodes in database"""
        with self.driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) as count")
            return result.single()["count"]
    
    def _get_sheet_type(self, sheet_name: str) -> str:
        """Map sheet name to Neo4j node label"""
        mapping = {
            "Project": "Project",
            "Stakeholder": "Stakeholder",
            "Client": "Client",
            "Role": "Role",
            "Feature": "Feature",
            "Requirement": "Requirement",
            "FunctioFFnal_Requirement": "FunctionalRequirement",
            "Goal": "Goal",
            "Constraint": "Constraint",
            "Risk": "Risk",
            "Budget": "Budget",
            "Line_Item": "LineItem",
            "Timeline": "Timeline",
            "Milestone": "Milestone",
            "Task": "Task",
            "Qual_Scenario": "QualityScenario",
        }
        return mapping.get(sheet_name, "RequirementNode")
    
    def _load_requirements(self):
        """Load nodes and relationships from Excel into Neo4j"""
        try:
            xls = pd.ExcelFile(self.excel_file, engine="openpyxl")
            
            key_sheets = [
                "Project", "Stakeholder", "Client", "Role", "Feature",
                "Requirement", "FunctioFFnal_Requirement", "Goal", "Constraint",
                "Risk", "Budget", "Line_Item", "Timeline", "Milestone", "Task", "Qual_Scenario"
            ]
            
            nodes_created = 0
            
            # Step 1: Load all nodes from sheets
            print("Loading nodes from Excel sheets...")
            for sheet_name in xls.sheet_names:
                if sheet_name not in key_sheets:
                    continue
                
                try:
                    df = pd.read_excel(self.excel_file, sheet_name=sheet_name, engine="openpyxl")
                    label = self._get_sheet_type(sheet_name)
                    
                    with self.driver.session() as session:
                        for idx, row in df.iterrows():
                            if row.isna().all():
                                continue
                            
                            # Extract node ID (usually first column or "id" column)
                            node_id = None
                            if "id" in df.columns:
                                node_id = str(row["id"]) if pd.notna(row.get("id")) else None
                            
                            if not node_id:
                                continue
                            
                            # Build properties from all columns
                            properties = {}
                            text_parts = []
                            
                            for col in df.columns:
                                if pd.notna(row[col]):
                                    value = str(row[col])
                                    properties[col.lower().replace(" ", "_")] = value
                                    text_parts.append(f"{col}: {value}")
                            
                            # Create text representation for embedding
                            text = f"Sheet: {sheet_name}\n" + "\n".join(text_parts)
                            
                            # Generate embedding
                            embedding = self.embedding_model.encode([text]).tolist()[0]
                            
                            # Store properties including embedding
                            properties["node_id"] = node_id
                            properties["sheet"] = sheet_name
                            properties["text"] = text
                            properties["embedding"] = embedding
                            
                            # Create node in Neo4j
                            query = f"""
                            MERGE (n:{label} {{node_id: $node_id}})
                            SET n += $properties
                            """
                            
                            session.run(query, node_id=node_id, properties=properties)
                            nodes_created += 1
                
                except Exception as e:
                    print(f"Error processing sheet {sheet_name}: {e}")
                    continue
            
            print(f"Created {nodes_created} nodes")
            
            # Step 2: Load relationships from Relationships sheet
            print("Loading relationships...")
            relationships_created = 0
            
            try:
                df_rel = pd.read_excel(self.excel_file, sheet_name="Relationships", engine="openpyxl")
                
                with self.driver.session() as session:
                    for _, row in df_rel.iterrows():
                        if pd.isna(row.get("start_id")) or pd.isna(row.get("end_id")) or pd.isna(row.get("type")):
                            continue
                        
                        start_id = str(row["start_id"])
                        end_id = str(row["end_id"])
                        rel_type = str(row["type"]).upper().replace(" ", "_")
                        
                        # Create relationship
                        query = f"""
                        MATCH (a {{node_id: $start_id}})
                        MATCH (b {{node_id: $end_id}})
                        MERGE (a)-[r:{rel_type}]->(b)
                        """
                        
                        session.run(query, start_id=start_id, end_id=end_id)
                        relationships_created += 1
                
                print(f"Created {relationships_created} relationships")
                
            except Exception as e:
                print(f"Error loading relationships: {e}")
            
            print("✓ Data loaded into Neo4j successfully")
            
        except Exception as e:
            print(f"Error loading requirements: {e}")
            raise
    
    def search(self, query: str, n_results: int = 5, filter_by_sheet_type: bool = True) -> List[Dict]:
        """
        Hybrid search: vector similarity + graph traversal
        
        Args:
            query: Search query
            n_results: Number of results to return
            filter_by_sheet_type: Whether to filter by detected intent
        
        Returns:
            List of search results with document, metadata, and distance
        """
        query_lower = query.lower()
        
        # Detect intent
        detected_sheets = self._detect_sheet_intent(query_lower)
        
        # Generate query embedding
        query_embedding = self.embedding_model.encode([query]).tolist()[0]
        
        # Vector search using cosine similarity
        results = self._vector_search(query_embedding, detected_sheets, n_results * 2)
        
        # Enhance with graph traversal - get related nodes
        enhanced_results = []
        for result in results[:n_results]:
            node_id = result["metadata"].get("node_id")
            if node_id:
                related = self._get_related_nodes(node_id, limit=2)
                result["metadata"]["related"] = related
            enhanced_results.append(result)
        
        return enhanced_results
    
    def _vector_search(self, query_embedding: List[float], detected_sheets: List[str], n_results: int) -> List[Dict]:
        """Vector search using cosine similarity on stored embeddings"""
        with self.driver.session() as session:
            # Build label filter if needed
            label_filter = ""
            if detected_sheets:
                labels = [self._get_sheet_type(sheet) for sheet in detected_sheets]
                label_filter = f"WHERE n:{':'.join(labels)}"
            
            # Get all nodes (or filtered by label)
            query = f"""
            MATCH (n)
            {label_filter}
            RETURN n
            LIMIT 1000
            """
            
            result = session.run(query)
            
            # Calculate cosine similarity for each node
            similarities = []
            for record in result:
                node = record["n"]
                if "embedding" not in node:
                    continue
                
                node_embedding = node["embedding"]
                
                # Calculate cosine similarity
                similarity = np.dot(query_embedding, node_embedding) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(node_embedding)
                )
                
                similarities.append((similarity, node))
            
            # Sort by similarity (highest first)
            similarities.sort(key=lambda x: x[0], reverse=True)
            
            # Format results
            results = []
            for similarity, node in similarities[:n_results]:
                results.append({
                    "document": node.get("text", ""),
                    "metadata": {
                        "node_id": node.get("node_id"),
                        "sheet": node.get("sheet", ""),
                        "sheet_type": self._get_sheet_type(node.get("sheet", "")),
                        "properties": dict(node)
                    },
                    "distance": 1 - similarity  # Convert similarity to distance
                })
            
            return results
    
    def _get_related_nodes(self, node_id: str, limit: int = 2) -> List[Dict]:
        """Get related nodes via graph traversal"""
        with self.driver.session() as session:
            query = """
            MATCH (n {node_id: $node_id})-[r]-(related)
            RETURN related, type(r) as rel_type
            LIMIT $limit
            """
            
            result = session.run(query, node_id=node_id, limit=limit)
            
            related = []
            for record in result:
                node = record["related"]
                related.append({
                    "node_id": node.get("node_id"),
                    "sheet": node.get("sheet", ""),
                    "text": node.get("text", "")[:100]  # Truncate for display
                })
            
            return related
    
    def _detect_sheet_intent(self, query: str) -> List[str]:
        """Detect which sheets the user is asking about"""
        intent_keywords = {
            "Stakeholder": ["stakeholder", "stakeholders", "people", "person", "who"],
            "Goal": ["goal", "goals", "objective", "objectives", "want", "need"],
            "Feature": ["feature", "features", "functionality", "do", "can"],
            "Requirement": ["requirement", "requirements", "req", "reqs"],
            "Risk": ["risk", "risks", "problem", "problems", "issue", "concern", "worry"],
            "Budget": ["budget", "cost", "costs", "money", "price"],
        }
        
        detected = []
        for sheet, keywords in intent_keywords.items():
            if any(kw in query for kw in keywords):
                detected.append(sheet)
        
        return detected
    
    def get_context(self, query: str, n_results: int = 3) -> str:
        """Get context from relevant requirements with graph relationships"""
        results = self.search(query, n_results=n_results, filter_by_sheet_type=True)
        
        if not results:
            return "No relevant information found."
        
        # Format with relationship context
        context_parts = []
        for result in results:
            doc = result["document"]
            related = result["metadata"].get("related", [])
            
            context_parts.append(doc)
            
            # Add related context from graph
            if related:
                context_parts.append("\nRelated:")
                for rel in related:
                    context_parts.append(f"  - {rel.get('text', '')[:100]}")
        
        return "\n".join(context_parts)
    
    def close(self):
        """Close Neo4j connection"""
        if self.driver:
            self.driver.close()
