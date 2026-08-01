"""
MCP DDGS — Serveur MCP pour la recherche web DuckDuckGo.

Expose des outils de recherche (texte, actualités, images) utilisables
par n'importe quel client MCP, notamment Goose.
"""

import anyio
from ddgs import DDGS
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

# ---------------------------------------------------------------------------
# Définition des outils
# ---------------------------------------------------------------------------

TOOLS = [
    Tool(
        name="ddgs_text_search",
        description="Recherche web texte via DuckDuckGo. Retourne titre, URL et extrait pour chaque résultat.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "La requête de recherche (ex: 'Python MCP protocol')",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Nombre maximum de résultats (défaut: 10, max: 20)",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="ddgs_news_search",
        description="Recherche d'actualités via DuckDuckGo. Retourne les articles récents correspondant à la requête.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "La requête (ex: 'intelligence artificielle 2026')",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Nombre maximum de résultats (défaut: 10, max: 20)",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="ddgs_image_search",
        description="Recherche d'images via DuckDuckGo. Retourne les URLs et descriptions des images trouvées.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "La requête de recherche d'images",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Nombre maximum de résultats (défaut: 10, max: 20)",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    ),
]

# ---------------------------------------------------------------------------
# Logique de recherche
# ---------------------------------------------------------------------------


def _search_text(query: str, max_results: int) -> str:
    max_results = min(max_results, 20)
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
    if not results:
        return f"Aucun résultat pour « {query} »."
    lines = [f"Résultats de recherche pour « {query} » :\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "Sans titre")
        href = r.get("href", "")
        body = r.get("body", "")
        lines.append(f"{i}. {title}")
        lines.append(f"   URL: {href}")
        lines.append(f"   {body}\n")
    return "\n".join(lines)


def _search_news(query: str, max_results: int) -> str:
    max_results = min(max_results, 20)
    with DDGS() as ddgs:
        results = list(ddgs.news(query, max_results=max_results))
    if not results:
        return f"Aucune actualité pour « {query} »."
    lines = [f"Actualités pour « {query} » :\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "Sans titre")
        url = r.get("url", "")
        source = r.get("source", "?")
        date = r.get("date", "?")
        body = r.get("body", "")
        lines.append(f"{i}. {title}")
        lines.append(f"   Source: {source} — {date}")
        lines.append(f"   URL: {url}")
        lines.append(f"   {body}\n")
    return "\n".join(lines)


def _search_images(query: str, max_results: int) -> str:
    max_results = min(max_results, 20)
    with DDGS() as ddgs:
        results = list(ddgs.images(query, max_results=max_results))
    if not results:
        return f"Aucune image pour « {query} »."
    lines = [f"Images pour « {query} » :\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "Sans titre")
        image_url = r.get("image", "")
        source = r.get("source", "?")
        lines.append(f"{i}. {title}")
        lines.append(f"   Image: {image_url}")
        lines.append(f"   Source: {source}\n")
    return "\n".join(lines)


HANDLERS = {
    "ddgs_text_search": _search_text,
    "ddgs_news_search": _search_news,
    "ddgs_image_search": _search_images,
}

# ---------------------------------------------------------------------------
# Serveur
# ---------------------------------------------------------------------------

server = Server(
    name="ddgs",
    version="1.0.0",
    title="DuckDuckGo Search",
    description="Recherche web, actualités et images via DuckDuckGo (gratuit, sans clé API).",
)


async def handle_list_tools(ctx, params: PaginatedRequestParams | None) -> ListToolsResult:
    return ListToolsResult(tools=TOOLS)


async def handle_call_tool(ctx, params: CallToolRequestParams) -> CallToolResult:
    handler = HANDLERS.get(params.name)
    if handler is None:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Outil inconnu : {params.name}")],
            isError=True,
        )
    try:
        arguments = params.arguments or {}
        query = arguments.get("query", "")
        max_results = arguments.get("max_results", 10)
        result_text = handler(query, max_results)
        return CallToolResult(content=[TextContent(type="text", text=result_text)])
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Erreur : {e}")],
            isError=True,
        )


server.add_request_handler("tools/list", PaginatedRequestParams, handle_list_tools)
server.add_request_handler("tools/call", CallToolRequestParams, handle_call_tool)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def run():
    anyio.run(main)


if __name__ == "__main__":
    run()
