"""Tool definitions and executor for the RAG-powered voice assistant."""

from __future__ import annotations

import json
import logging

from src.services.rag import KnowledgeBase

logger = logging.getLogger(__name__)

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search the NovaTech knowledge base for relevant information. "
                "Use this for any question about NovaTech, NovaBoard, pricing, "
                "features, API, troubleshooting, or security."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to find relevant information",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_source_details",
            "description": (
                "Get detailed source information for a document from the knowledge base. "
                "Use this when the user asks where information came from or wants to "
                "see the source reference."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "string",
                        "description": (
                            "The source document filename "
                            "(e.g., 'pricing-plans.md', 'security-compliance.md')"
                        ),
                    },
                },
                "required": ["document_id"],
            },
        },
    },
]


class ToolExecutor:
    """Executes tool calls by dispatching to the appropriate KnowledgeBase method."""

    def __init__(self, knowledge_base: KnowledgeBase) -> None:
        self._kb = knowledge_base

    async def execute(self, name: str, arguments: str) -> str:
        """Execute a tool call and return the result as a JSON string.

        Args:
            name: The function name to execute.
            arguments: JSON string of the function arguments.

        Returns:
            JSON string with the tool result.
        """
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            return json.dumps({"error": f"Invalid arguments: {arguments}"})

        if name == "search_knowledge_base":
            return await self._search_knowledge_base(args)
        elif name == "get_source_details":
            return self._get_source_details(args)
        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    async def _search_knowledge_base(self, args: dict) -> str:
        query = args.get("query", "")
        if not query:
            return json.dumps({"error": "Query is required"})

        results = await self._kb.search(query)
        logger.info("Tool search_knowledge_base(%r) -> %d results", query, len(results))

        return json.dumps({
            "results": [
                {
                    "content": r.content,
                    "source": r.source,
                    "section": r.section,
                    "relevance_score": round(r.score, 3),
                }
                for r in results
            ],
        })

    def _get_source_details(self, args: dict) -> str:
        document_id = args.get("document_id", "")
        if not document_id:
            # List all available documents.
            docs = self._kb.list_documents()
            return json.dumps({"available_documents": docs})

        details = self._kb.get_source_details(document_id)
        logger.info("Tool get_source_details(%r) -> %s", document_id, details)
        return json.dumps(details)
