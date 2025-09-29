// Constraints
DROP CONSTRAINT document_doc_id IF EXISTS;
CREATE CONSTRAINT document_doc_id IF NOT EXISTS
FOR (d:Document)
REQUIRE d.doc_id IS UNIQUE;

CREATE CONSTRAINT file_sha256 IF NOT EXISTS
FOR (f:File)
REQUIRE f.sha256 IS UNIQUE;

CREATE CONSTRAINT email_message_id IF NOT EXISTS
FOR (e:Email)
REQUIRE e.message_id IS UNIQUE;

CREATE CONSTRAINT page_id IF NOT EXISTS
FOR (p:Page)
REQUIRE p.page_id IS UNIQUE;

CREATE CONSTRAINT block_id IF NOT EXISTS
FOR (b:Block)
REQUIRE b.block_id IS UNIQUE;

CREATE CONSTRAINT image_id IF NOT EXISTS
FOR (i:Image)
REQUIRE i.image_id IS UNIQUE;

CREATE CONSTRAINT audio_id IF NOT EXISTS
FOR (a:Audio)
REQUIRE a.audio_id IS UNIQUE;

CREATE CONSTRAINT transcript_id IF NOT EXISTS
FOR (t:Transcript)
REQUIRE t.transcript_id IS UNIQUE;

CREATE CONSTRAINT person_id IF NOT EXISTS
FOR (p:Person)
REQUIRE p.person_id IS UNIQUE;

CREATE CONSTRAINT organization_id IF NOT EXISTS
FOR (o:Organization)
REQUIRE o.org_id IS UNIQUE;

CREATE CONSTRAINT project_id IF NOT EXISTS
FOR (p:Project)
REQUIRE p.project_id IS UNIQUE;

CREATE CONSTRAINT event_id IF NOT EXISTS
FOR (e:Event)
REQUIRE e.event_id IS UNIQUE;

CREATE CONSTRAINT place_id IF NOT EXISTS
FOR (pl:Place)
REQUIRE pl.place_id IS UNIQUE;

// Indexes
CREATE BTREE INDEX document_source IF NOT EXISTS FOR (d:Document) ON (d.source);
CREATE BTREE INDEX document_validity IF NOT EXISTS FOR (d:Document) ON (d.valid_from, d.valid_to);
CREATE BTREE INDEX email_thread_id IF NOT EXISTS FOR (e:Email) ON (e.thread_id);
CREATE BTREE INDEX block_type IF NOT EXISTS FOR (b:Block) ON (b.block_type);
CREATE BTREE INDEX image_capture_time IF NOT EXISTS FOR (i:Image) ON (i.capture_time_utc);
CREATE BTREE INDEX event_time IF NOT EXISTS FOR (e:Event) ON (e.start_time);

// Fulltext search indexes (create if missing via APOC)
CALL {
  WITH "documentTextFulltext" AS idxName
  CALL db.index.fulltext.list() YIELD name
  WITH collect(name) AS names, idxName
  CALL apoc.do.when(
    idxName IN names,
    'RETURN true AS created',
    'CALL db.index.fulltext.createNodeIndex($idxName, $labels, $properties, $config) RETURN true AS created',
    {
      idxName: idxName,
      labels: ['Document', 'Block', 'Email', 'Transcript'],
      properties: ['text_content', 'title', 'snippet'],
      config: { analyzer: 'standard' }
    }
  ) YIELD value
  RETURN value.created AS created
};

CALL {
  WITH "entityNameFulltext" AS idxName
  CALL db.index.fulltext.list() YIELD name
  WITH collect(name) AS names, idxName
  CALL apoc.do.when(
    idxName IN names,
    'RETURN true AS created',
    'CALL db.index.fulltext.createNodeIndex($idxName, $labels, $properties, $config) RETURN true AS created',
    {
      idxName: idxName,
      labels: ['Person', 'Organization', 'Project', 'Place'],
      properties: ['full_name', 'org_name', 'project_name', 'place_name'],
      config: { analyzer: 'standard' }
    }
  ) YIELD value
  RETURN value.created AS created
};
