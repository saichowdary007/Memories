from __future__ import annotations

from typing import Any, Dict, List


class GraphQueries:
    @staticmethod
    def upsert_document() -> str:
        return (
            "MERGE (d:Document {doc_id: $doc_id}) "
            "SET d += $props, d.system_from = coalesce(d.system_from, datetime()), d.system_to = datetime()"
        )

    @staticmethod
    def create_document_relationships() -> str:
        return (
            "UNWIND $relations AS rel "
            "MATCH (src {doc_id: rel.source_id}) "
            "MATCH (dst {doc_id: rel.target_id}) "
            "MERGE (src)-[:VERSION_CHAIN]->(dst)"
        )

    @staticmethod
    def upsert_file() -> str:
        return (
            "MERGE (f:File {sha256: $sha256}) "
            "SET f += $props"
        )

    @staticmethod
    def link_document_file() -> str:
        return (
            "MATCH (d:Document {doc_id: $doc_id}) "
            "MATCH (f:File {sha256: $sha256}) "
            "MERGE (d)-[:HAS_FILE]->(f)"
        )

    @staticmethod
    def upsert_page() -> str:
        return (
            "MERGE (p:Page {page_id: $page_id}) "
            "SET p += $props"
        )

    @staticmethod
    def link_page_document() -> str:
        return (
            "MATCH (p:Page {page_id: $page_id}) "
            "MATCH (d:Document {doc_id: $doc_id}) "
            "MERGE (p)-[:BELONGS_TO]->(d)"
        )

    @staticmethod
    def upsert_block() -> str:
        return (
            "MERGE (b:Block {block_id: $block_id}) "
            "SET b += $props"
        )

    @staticmethod
    def set_block_vector() -> str:
        return "MATCH (b:Block {block_id: $block_id}) SET b.text_vector = $vector"

    @staticmethod
    def link_block_page() -> str:
        return (
            "MATCH (b:Block {block_id: $block_id}) "
            "MATCH (p:Page {page_id: $page_id}) "
            "MERGE (b)-[:CHILD_OF]->(p)"
        )

    @staticmethod
    def link_files_near_duplicate() -> str:
        return (
            "MATCH (a:File {sha256: $source_sha}) "
            "MATCH (b:File {sha256: $target_sha}) "
            "MERGE (a)-[:NEAR_DUPLICATE]->(b)"
        )

    @staticmethod
    def link_audio_transcript() -> str:
        return (
            "MATCH (a:Audio {audio_id: $audio_id}) MATCH (t:Transcript {transcript_id: $transcript_id}) "
            "MERGE (a)-[:HAS_TRANSCRIPT]->(t)"
        )

    @staticmethod
    def link_image_file() -> str:
        return (
            "MATCH (i:Image {image_id: $image_id}) MATCH (f:File {sha256: $sha256}) "
            "MERGE (i)-[:DERIVED_FROM]->(f)"
        )

    @staticmethod
    def upsert_email() -> str:
        return (
            "MERGE (e:Email {message_id: $message_id}) "
            "SET e += $props"
        )

    @staticmethod
    def upsert_image() -> str:
        return (
            "MERGE (i:Image {image_id: $image_id}) "
            "SET i += $props"
        )

    @staticmethod
    def upsert_audio() -> str:
        return (
            "MERGE (a:Audio {audio_id: $audio_id}) SET a += $props"
        )

    @staticmethod
    def link_email_person(rel_type: str) -> str:
        return (
            f"MATCH (e:Email {{message_id: $message_id}}) MATCH (p:Person {{person_id: $person_id}}) "
            f"MERGE (e)-[:{rel_type.upper()}]->(p)"
        )

    @staticmethod
    def link_email_document() -> str:
        return (
            "MATCH (e:Email {message_id: $message_id}) MATCH (d:Document {doc_id: $doc_id}) "
            "MERGE (e)-[:ATTACHMENT]->(d)"
        )

    @staticmethod
    def upsert_person() -> str:
        return (
            "MERGE (p:Person {person_id: $person_id}) "
            "SET p += $props"
        )

    @staticmethod
    def upsert_transcript() -> str:
        return (
            "MERGE (t:Transcript {transcript_id: $transcript_id}) "
            "SET t += $props"
        )

    @staticmethod
    def upsert_entity(label: str) -> str:
        return (
            f"MERGE (n:{label} {{id: $id}}) SET n += $props"
        )

    @staticmethod
    def upsert_project() -> str:
        return "MERGE (p:Project {project_id: $project_id}) SET p += $props"

    @staticmethod
    def upsert_organization() -> str:
        return "MERGE (o:Organization {org_id: $org_id}) SET o += $props"

    @staticmethod
    def upsert_place() -> str:
        return "MERGE (pl:Place {place_id: $place_id}) SET pl += $props"

    @staticmethod
    def upsert_event() -> str:
        return "MERGE (e:Event {event_id: $event_id}) SET e += $props"

    @staticmethod
    def match_related_entities() -> str:
        return (
            "MATCH (n) WHERE elementId(n) IN $element_ids "
            "WITH DISTINCT n OPTIONAL MATCH (n)-[r*1..2]-(m) "
            "RETURN DISTINCT m LIMIT $limit"
        )

    @staticmethod
    def bm25_search() -> str:
        return (
            "CALL db.index.fulltext.queryNodes('documentTextFulltext', $query)"
            " YIELD node, score RETURN node, score LIMIT $limit"
        )

    @staticmethod
    def entity_search() -> str:
        return (
            "CALL db.index.fulltext.queryNodes('entityNameFulltext', $query)"
            " YIELD node, score RETURN node, score LIMIT $limit"
        )
