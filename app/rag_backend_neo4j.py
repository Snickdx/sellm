"""
Hybrid Neo4j RAG Implementation
Combines vector search with graph relationships for better context retrieval
"""
# Apply pytree compatibility fix before importing sentence_transformers
try:
    from app import fix_pytree  # noqa: F401
except ImportError:
    pass

import warnings

warnings.filterwarnings(
    "ignore",
    message=r".*resume_download.*",
    category=FutureWarning,
    module=r"huggingface_hub\.file_download",
)

import hashlib
import pandas as pd
from typing import List, Dict, Optional
import numpy as np

from app.embeddings import get_embedding_model

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
        self._scenario_graph_hash: Optional[str] = None
        self._vector_index_ready = False
        
        # Shared embedding singleton (avoid dual SentenceTransformer loads)
        print("Loading embedding model...")
        self.embedding_model = get_embedding_model()
        
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

        self._ensure_vector_index()
        
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
    
    def _ensure_vector_index(self) -> None:
        """Create a Neo4j vector index for Excel embeddings when the server supports it."""
        try:
            with self.driver.session() as session:
                session.run(
                    """
                    CREATE VECTOR INDEX excel_embeddings IF NOT EXISTS
                    FOR (n:Requirement)
                    ON n.embedding
                    OPTIONS {
                      indexConfig: {
                        `vector.dimensions`: 384,
                        `vector.similarity_function`: 'cosine'
                      }
                    }
                    """
                )
            self._vector_index_ready = True
            print("✓ Neo4j vector index excel_embeddings ready")
        except Exception as exc:  # noqa: BLE001 — older Neo4j / missing labels
            self._vector_index_ready = False
            print(f"⚠ Neo4j vector index unavailable (will use capped fallback): {exc}")

    def upsert_scenario_graph(self, packages, *, content_hash: Optional[str] = None) -> int:
        """Translate scenario package facts into a Neo4j domain graph.

        Workflow:
        1. Build a deterministic graph plan (`app.scenarios.neo4j_graph`)
        2. Map flat KnowledgeFacts onto Excel-aligned typed labels
           (Requirement / Constraint / Task / …) under ``ScenarioPack``
        3. Write package + provenance + domain edges without touching Excel-only nodes

        Returns total relationship count created for scenario packages.
        """
        from app.scenarios.neo4j_graph import (
            LEGACY_SCENARIO_LABELS,
            SCENARIO_PACK_LABEL,
            build_scenario_graph_plan,
            iter_embed_texts,
        )

        digest = content_hash or hashlib.sha256(
            "|".join(
                f"{p.meta.slug}:{p.meta.version}:{len(p.personas)}:{len(p.facts)}"
                for p in packages
            ).encode("utf-8")
        ).hexdigest()
        if self._scenario_graph_hash == digest:
            print("✓ Scenario graph unchanged — skipping Neo4j reindex")
            return 0

        plans = [build_scenario_graph_plan(package) for package in packages]
        edges = 0
        with self.driver.session() as session:
            # Wipe scenario-pack subgraph only (leave Excel-only nodes alone).
            session.run(f"MATCH (n:{SCENARIO_PACK_LABEL}) DETACH DELETE n")
            for label in LEGACY_SCENARIO_LABELS:
                session.run(f"MATCH (n:{label}) DETACH DELETE n")

            for plan in plans:
                embed_map = {}
                texts = list(iter_embed_texts(plan))
                if texts:
                    vectors = self.embedding_model.encode([t for _, t in texts]).tolist()
                    embed_map = {node_id: vec for (node_id, _), vec in zip(texts, vectors)}

                for node in plan.nodes:
                    labels = ":".join(node.labels)
                    # Keys are controlled vocabulary from the translator.
                    key_props = ", ".join(f"{k}: ${k}" for k in node.key.keys())
                    props = dict(node.props)
                    props.pop("needs_embedding", None)
                    node_id = node.key.get("node_id")
                    if node_id and node_id in embed_map:
                        props["embedding"] = embed_map[node_id]
                    params = {**node.key, "properties": props}
                    session.run(
                        f"""
                        MERGE (n:{labels} {{{key_props}}})
                        SET n += $properties
                        """,
                        **params,
                    )

                for edge in plan.edges:
                    from_labels = ":".join(edge.from_labels)
                    to_labels = ":".join(edge.to_labels)
                    from_key = ", ".join(f"{k}: $from_{k}" for k in edge.from_key.keys())
                    to_key = ", ".join(f"{k}: $to_{k}" for k in edge.to_key.keys())
                    params = {
                        **{f"from_{k}": v for k, v in edge.from_key.items()},
                        **{f"to_{k}": v for k, v in edge.to_key.items()},
                        "edge_props": edge.props or {},
                    }
                    session.run(
                        f"""
                        MATCH (a:{from_labels} {{{from_key}}})
                        MATCH (b:{to_labels} {{{to_key}}})
                        MERGE (a)-[r:{edge.rel_type}]->(b)
                        SET r += $edge_props
                        """,
                        **params,
                    )
                    edges += 1

        self._ensure_scenario_vector_index()
        self._scenario_graph_hash = digest
        fact_total = sum(p.stats.get("facts", 0) for p in plans)
        print(
            f"✓ Indexed {edges} scenario graph relationships "
            f"({fact_total} typed facts) into Neo4j"
        )
        return edges

    def _ensure_scenario_vector_index(self) -> None:
        """Vector index for scenario-pack embeddings (neo4j mode)."""
        try:
            with self.driver.session() as session:
                session.run(
                    """
                    CREATE VECTOR INDEX scenario_pack_embeddings IF NOT EXISTS
                    FOR (n:ScenarioPack)
                    ON n.embedding
                    OPTIONS {
                      indexConfig: {
                        `vector.dimensions`: 384,
                        `vector.similarity_function`: 'cosine'
                      }
                    }
                    """
                )
            print("✓ Neo4j vector index scenario_pack_embeddings ready")
        except Exception as exc:  # noqa: BLE001
            print(f"⚠ Neo4j scenario_pack vector index unavailable: {exc}")

    def search(
        self,
        query: str,
        n_results: int = 5,
        filter_by_sheet_type: bool = True,
        scenario_slug: str | None = None,
        persona_key: str | None = None,
    ) -> List[Dict]:
        """
        Hybrid search: vector similarity + graph traversal.
        When scenario_slug + persona_key are set, search ScenarioPack facts that persona KNOWS.
        """
        query_embedding = self.embedding_model.encode([query]).tolist()[0]

        if scenario_slug and persona_key:
            results = self._vector_search_scenario(
                query_embedding,
                scenario_slug=scenario_slug,
                persona_key=persona_key,
                n_results=n_results * 2,
            )
            enhanced = []
            for result in results[:n_results]:
                node_id = result["metadata"].get("node_id")
                if node_id:
                    related = self._get_related_nodes(node_id, limit=2)
                    result["metadata"]["related"] = related
                enhanced.append(result)
            return enhanced

        query_lower = query.lower()
        detected_sheets = self._detect_sheet_intent(query_lower) if filter_by_sheet_type else []
        results = self._vector_search(query_embedding, detected_sheets, n_results * 2)

        enhanced_results = []
        for result in results[:n_results]:
            node_id = result["metadata"].get("node_id")
            if node_id:
                related = self._get_related_nodes(node_id, limit=2)
                result["metadata"]["related"] = related
            enhanced_results.append(result)

        return enhanced_results

    def _vector_search_scenario(
        self,
        query_embedding: List[float],
        *,
        scenario_slug: str,
        persona_key: str,
        n_results: int,
    ) -> List[Dict]:
        """Vector search over ScenarioPack knowledge nodes known by a stakeholder."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (p:ScenarioPack:Stakeholder {
                    key: $persona_key,
                    scenario_slug: $scenario_slug
                })-[:KNOWS]->(n:ScenarioPack)
                WHERE n.embedding IS NOT NULL
                RETURN n
                """,
                persona_key=persona_key,
                scenario_slug=scenario_slug,
            )
            similarities = []
            for record in result:
                node = record["n"]
                if "embedding" not in node:
                    continue
                node_embedding = node["embedding"]
                similarity = np.dot(query_embedding, node_embedding) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(node_embedding) + 1e-9
                )
                similarities.append((similarity, node))

            similarities.sort(key=lambda x: x[0], reverse=True)
            results = []
            for similarity, node in similarities[:n_results]:
                results.append(
                    {
                        "document": node.get("text", ""),
                        "metadata": {
                            "node_id": node.get("node_id"),
                            "sheet": node.get("sheet", "Requirement"),
                            "sheet_type": node.get("sheet_type") or node.get("kind") or "requirement",
                            "category": node.get("category"),
                            "kind": node.get("kind"),
                            "family": node.get("family"),
                            "scenario_slug": node.get("scenario_slug"),
                            "fact_id": node.get("fact_id"),
                            "persona_key": persona_key,
                            "source": "scenario",
                        },
                        "distance": 1 - similarity,
                    }
                )
            return results

    def _vector_search(self, query_embedding: List[float], detected_sheets: List[str], n_results: int) -> List[Dict]:
        """Vector search via Neo4j index when available; otherwise capped Python cosine."""
        with self.driver.session() as session:
            if self._vector_index_ready:
                try:
                    result = session.run(
                        """
                        CALL db.index.vector.queryNodes('excel_embeddings', $k, $embedding)
                        YIELD node, score
                        WHERE NOT node:ScenarioPack
                        RETURN node AS n, score
                        LIMIT $k
                        """,
                        k=max(n_results * 3, n_results),
                        embedding=query_embedding,
                    )
                    results = []
                    for record in result:
                        node = record["n"]
                        score = float(record["score"])
                        sheet = node.get("sheet", "")
                        if detected_sheets:
                            labels = {self._get_sheet_type(s) for s in detected_sheets}
                            if labels and self._get_sheet_type(sheet) not in labels:
                                continue
                        results.append(
                            {
                                "document": node.get("text", ""),
                                "metadata": {
                                    "node_id": node.get("node_id"),
                                    "sheet": sheet,
                                    "sheet_type": self._get_sheet_type(sheet),
                                    "properties": dict(node),
                                },
                                "distance": 1 - score,
                            }
                        )
                        if len(results) >= n_results:
                            break
                    if results:
                        return results
                except Exception as exc:  # noqa: BLE001
                    print(f"⚠ Neo4j vector query failed, using capped fallback: {exc}")
                    self._vector_index_ready = False

            pack_exclude = "NOT n:ScenarioPack"
            label_filter = f"WHERE {pack_exclude} AND n.embedding IS NOT NULL"
            if detected_sheets:
                labels = [self._get_sheet_type(sheet) for sheet in detected_sheets]
                or_labels = " OR ".join(f"n:{label}" for label in labels)
                label_filter = f"WHERE ({or_labels}) AND {pack_exclude} AND n.embedding IS NOT NULL"

            query = f"""
            MATCH (n)
            {label_filter}
            RETURN n
            LIMIT 200
            """
            result = session.run(query)
            similarities = []
            for record in result:
                node = record["n"]
                node_embedding = node.get("embedding")
                if not node_embedding:
                    continue
                similarity = np.dot(query_embedding, node_embedding) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(node_embedding) + 1e-9
                )
                similarities.append((similarity, node))
            similarities.sort(key=lambda x: x[0], reverse=True)
            results = []
            for similarity, node in similarities[:n_results]:
                results.append(
                    {
                        "document": node.get("text", ""),
                        "metadata": {
                            "node_id": node.get("node_id"),
                            "sheet": node.get("sheet", ""),
                            "sheet_type": self._get_sheet_type(node.get("sheet", "")),
                            "properties": dict(node),
                        },
                        "distance": 1 - similarity,
                    }
                )
            return results

    def _related_record(self, node, rel_type: str) -> Dict:
        labels = list(node.labels) if hasattr(node, "labels") else []
        return {
            "node_id": (
                node.get("node_id")
                or node.get("criterion_id")
                or node.get("decision_id")
                or node.get("cue_id")
            ),
            "sheet": node.get("sheet", ""),
            "rel_type": rel_type,
            "labels": labels,
            "text": (node.get("text") or node.get("chosen") or node.get("cue_id") or "")[:100],
        }

    def _get_related_nodes(self, node_id: str, limit: int = 2) -> List[Dict]:
        """Get related nodes via graph traversal (Excel + YAML scenario edges)."""
        with self.driver.session() as session:
            related: List[Dict] = []
            seen: set = set()

            def _consume(records, rel_type: Optional[str] = None) -> None:
                for record in records:
                    node = record["related"]
                    item = self._related_record(
                        node, rel_type or record.get("rel_type") or "RELATED"
                    )
                    rid = item.get("node_id")
                    if not rid or rid in seen:
                        continue
                    seen.add(rid)
                    related.append(item)
                    if len(related) >= limit:
                        return

            # Domain-style scenario expansion (closer to Excel relationship enrichment).
            _consume(
                session.run(
                    """
                    MATCH (n:ScenarioPack {node_id: $node_id})-[:IN_CATEGORY]->(:Category)
                          <-[:IN_CATEGORY]-(related:ScenarioPack)
                    WHERE related.node_id <> $node_id AND related.embedding IS NOT NULL
                    RETURN related
                    LIMIT $limit
                    """,
                    node_id=node_id,
                    limit=limit,
                ),
                "SAME_CATEGORY",
            )
            if len(related) < limit:
                _consume(
                    session.run(
                        """
                        MATCH (n:ScenarioPack {node_id: $node_id})-[:IN_FAMILY]->(:FactFamily)
                              <-[:IN_FAMILY]-(related:ScenarioPack)
                        WHERE related.node_id <> $node_id AND related.embedding IS NOT NULL
                        RETURN related
                        LIMIT $limit
                        """,
                        node_id=node_id,
                        limit=limit,
                    ),
                    "SAME_FAMILY",
                )
            if len(related) < limit:
                _consume(
                    session.run(
                        """
                        MATCH (n:ScenarioPack {node_id: $node_id})-[:HAS_CRITERION]->(related:AcceptanceCriterion)
                        RETURN related
                        LIMIT $limit
                        """,
                        node_id=node_id,
                        limit=limit,
                    ),
                    "HAS_CRITERION",
                )
            if related:
                return related[:limit]

            # Excel Relationships sheet / generic one-hop neighbors (non-pack nodes).
            _consume(
                session.run(
                    """
                    MATCH (n {node_id: $node_id})-[r]-(related)
                    WHERE NOT related:ScenarioPack
                    RETURN related, type(r) as rel_type
                    LIMIT $limit
                    """,
                    node_id=node_id,
                    limit=limit,
                )
            )
            return related[:limit]
    
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
