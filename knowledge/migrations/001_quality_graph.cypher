CREATE CONSTRAINT knowledge_project_id IF NOT EXISTS
FOR (n:KnowledgeProject) REQUIRE n.project_id IS UNIQUE;

CREATE CONSTRAINT knowledge_entity_id IF NOT EXISTS
FOR (n:Entity) REQUIRE (n.project_id, n.entity_id) IS UNIQUE;

CREATE CONSTRAINT knowledge_name_key IF NOT EXISTS
FOR (n:EntityName) REQUIRE (n.project_id, n.entity_type, n.compact, n.key) IS UNIQUE;

CREATE CONSTRAINT knowledge_chunk_id IF NOT EXISTS
FOR (n:SourceChunk) REQUIRE (n.project_id, n.chunk_id) IS UNIQUE;

CREATE CONSTRAINT knowledge_evidence_id IF NOT EXISTS
FOR (n:Evidence) REQUIRE (n.project_id, n.evidence_id) IS UNIQUE;

CREATE CONSTRAINT knowledge_edge_id IF NOT EXISTS
FOR ()-[r:RELATIONSHIP]-() REQUIRE (r.project_id, r.relationship_id) IS UNIQUE;

CREATE INDEX knowledge_evidence_edge IF NOT EXISTS
FOR (n:Evidence) ON (n.project_id, n.relationship_id);

CREATE INDEX knowledge_evidence_chunk IF NOT EXISTS
FOR (n:Evidence) ON (n.project_id, n.chunk_id);
