"""
MCP DDGS — Serveur MCP pour la recherche web DuckDuckGo.

Expose des outils de recherche (texte, actualités, images) utilisables
par n'importe quel client MCP, notamment Goose.
"""

import gzip
import json
import urllib.request
from typing import Any, cast

import anyio
from ddgs import DDGS
from lxml import html as lxml_html
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
from trafilatura import bare_extraction, fetch_url
from trafilatura.settings import Document

# ---------------------------------------------------------------------------
# Définition des outils
# ---------------------------------------------------------------------------

TOOLS = [
    Tool(
        name="ddgs_text_search",
        description="Recherche web texte (méta-recherche: duckduckgo, bing, google, brave, yahoo, yandex, startpage, mojeek, wikipedia). Retourne titre, URL et extrait pour chaque résultat.",
        input_schema={
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
                "backend": {
                    "type": "string",
                    "description": "Moteur de recherche à interroger (défaut: auto). Plusieurs moteurs possibles, séparés par des virgules (ex: 'bing,google').",
                    "enum": ["auto", "bing", "brave", "duckduckgo", "google", "grokipedia", "mojeek", "startpage", "yandex", "yahoo", "wikipedia"],
                    "default": "auto",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="ddgs_news_search",
        description="Recherche d'actualités (méta-recherche: duckduckgo, bing, yahoo). Retourne les articles récents correspondant à la requête.",
        input_schema={
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
                "backend": {
                    "type": "string",
                    "description": "Moteur de recherche à interroger (défaut: auto). Plusieurs moteurs possibles, séparés par des virgules.",
                    "enum": ["auto", "bing", "duckduckgo", "yahoo"],
                    "default": "auto",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="ddgs_image_search",
        description="Recherche d'images (méta-recherche: duckduckgo, bing). Retourne les URLs et descriptions des images trouvées.",
        input_schema={
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
                "backend": {
                    "type": "string",
                    "description": "Moteur de recherche à interroger (défaut: auto). Plusieurs moteurs possibles, séparés par des virgules.",
                    "enum": ["auto", "bing", "duckduckgo"],
                    "default": "auto",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="ddgs_fetch_url",
        description="Extrait le contenu d'une page web (URL) : texte principal propre + données structurées (prix, produit) si présentes — prêt à être lu par un LLM. Mode « full » pour tout le texte visible (pages produit).",
        input_schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "L'URL de la page à extraire",
                },
                "mode": {
                    "type": "string",
                    "description": "Mode d'extraction : « article » (texte principal nettoyé — défaut) ou « full » (tout le texte visible, recommandé pour les pages produit/prix)",
                    "enum": ["article", "full"],
                    "default": "article",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Limite en caractères du texte retourné (défaut: 100000 — protection contre les pages démesurées)",
                    "default": 100000,
                },
            },
            "required": ["url"],
        },
    ),
]

# ---------------------------------------------------------------------------
# Logique de recherche
# ---------------------------------------------------------------------------


def _search_text(arguments: dict[str, Any]) -> str:
    query = arguments.get("query", "")
    max_results = min(int(arguments.get("max_results", 10)), 20)
    backend = arguments.get("backend", "auto")
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results, backend=backend))
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


def _search_news(arguments: dict[str, Any]) -> str:
    query = arguments.get("query", "")
    max_results = min(int(arguments.get("max_results", 10)), 20)
    backend = arguments.get("backend", "auto")
    with DDGS() as ddgs:
        results = list(ddgs.news(query, max_results=max_results, backend=backend))
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


def _search_images(arguments: dict[str, Any]) -> str:
    query = arguments.get("query", "")
    max_results = min(int(arguments.get("max_results", 10)), 20)
    backend = arguments.get("backend", "auto")
    with DDGS() as ddgs:
        results = list(ddgs.images(query, max_results=max_results, backend=backend))
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


def _download(url: str) -> str | None:
    """Télécharge une page : d'abord via trafilatura, puis repli sur urllib
    (qui respecte les variables d'environnement de proxy http_proxy/https_proxy)."""
    try:
        downloaded = fetch_url(url)
    except Exception:
        downloaded = None
    if downloaded is not None:
        return downloaded
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "identity",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            charset = resp.headers.get_content_charset() or "utf-8"
            return data.decode(charset, errors="replace")
    except (OSError, ValueError):
        return None


TRUNCATION_MARKER = "\n[… tronqué …]"

AVAILABILITY_LABELS = {
    "https://schema.org/InStock": "En stock",
    "https://schema.org/OutOfStock": "Rupture de stock",
    "https://schema.org/PreOrder": "Précommande",
    "https://schema.org/BackOrder": "En réapprovisionnement",
    "InStock": "En stock",
    "OutOfStock": "Rupture de stock",
}

_LD_FIELD_LABELS = {
    "price": "Prix",
    "lowPrice": "Prix min",
    "highPrice": "Prix max",
    "priceCurrency": "Devise",
    "availability": "Disponibilité",
    "priceValidUntil": "Prix valable jusqu'au",
    "offerCount": "Nombre d'offres",
    "itemCondition": "État",
}


def _walk_ld_json(node: Any, lines: list[str]) -> None:
    """Parcourt récursivement un bloc JSON-LD et collecte les infos produit/prix."""
    if isinstance(node, dict):
        types = node.get("@type")
        if not isinstance(types, list):
            types = [types] if types else []
        if "Product" in types:
            if node.get("name"):
                lines.append(f"- Produit : {node['name']}")
            if node.get("sku"):
                lines.append(f"- SKU : {node['sku']}")
            brand = node.get("brand")
            if isinstance(brand, dict) and brand.get("name"):
                lines.append(f"- Marque : {brand['name']}")
        if any(t in types for t in ("Offer", "AggregateOffer", "PriceSpecification")):
            for field, label in _LD_FIELD_LABELS.items():
                val = node.get(field)
                if val is None:
                    continue
                if field == "availability":
                    val = AVAILABILITY_LABELS.get(str(val), str(val).rsplit("/", 1)[-1])
                lines.append(f"- {label} : {val}")
        for value in node.values():
            _walk_ld_json(value, lines)
    elif isinstance(node, list):
        for item in node:
            _walk_ld_json(item, lines)


def _extract_structured_data(html_source: str) -> str:
    """Extrait les infos produit/prix : JSON-LD, meta og:price/product:price, microdata itemprop."""
    try:
        tree = lxml_html.fromstring(html_source)
    except Exception:
        return ""

    lines: list[str] = []
    for script in tree.xpath("//script[@type='application/ld+json']"):
        try:
            data = json.loads(script.text or "")
        except (json.JSONDecodeError, ValueError):
            continue
        _walk_ld_json(data, lines)

    for prop in ("product:price:amount", "og:price:amount", "product:price:currency", "og:price:currency"):
        for meta in tree.xpath(f"//meta[@property='{prop}']"):
            content = meta.get("content")
            if content:
                lines.append(f"- {prop} : {content}")

    for el in tree.xpath("//*[@itemprop='price'] | //*[@itemprop='priceCurrency']"):
        value = el.get("content") or (el.text or "").strip()
        if value:
            lines.append(f"- {el.get('itemprop')} : {value}")

    unique: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if line not in seen:
            seen.add(line)
            unique.append(line)
    if not unique:
        return ""
    return "Données structurées (produit / prix) :\n" + "\n".join(unique)


def _full_text(html_source: str) -> str:
    """Tout le texte visible de la page (aucun filtrage éditorial)."""
    try:
        tree = lxml_html.fromstring(html_source)
        for tag in list(tree.iter("script", "style", "noscript", "template", "head")):
            tag.drop_tree()
        text = tree.text_content()
    except Exception:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def _page_title(html_source: str) -> str | None:
    try:
        tree = lxml_html.fromstring(html_source)
        title = tree.findtext(".//title")
        return title.strip() if title else None
    except Exception:
        return None


def _fetch_url(arguments: dict[str, Any]) -> str:
    url = arguments.get("url", "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"URL invalide : « {url} » — doit commencer par http:// ou https://.")
    mode = arguments.get("mode", "article")
    if mode not in ("article", "full"):
        raise ValueError(f"Mode invalide : « {mode} » — doit être « article » ou « full ».")
    max_chars = max(1, min(int(arguments.get("max_chars", 100000)), 100000))

    downloaded = _download(url)
    if downloaded is None:
        return f"Impossible de télécharger « {url} » (accès refusé, page introuvable ou erreur réseau)."

    if mode == "full":
        title = _page_title(downloaded)
        body = _full_text(downloaded)
    else:
        doc = cast(
            Document | None,
            bare_extraction(
                downloaded,
                url=url,
                favor_precision=True,
                include_comments=False,
                include_tables=False,
                with_metadata=True,
            ),
        )
        if doc is None:
            doc = cast(
                Document | None,
                bare_extraction(downloaded, url=url, favor_precision=False, include_tables=True),
            )
        title = doc.title if doc else _page_title(downloaded)
        body = (doc.text or "") if doc else ""

    structured = _extract_structured_data(downloaded)
    structured_section = f"\n\n{structured}" if structured else ""
    header = f"Titre : {title}\nURL : {url}\n\n" if title else f"URL : {url}\n\n"

    if not body and not structured:
        return f"Aucun contenu textuel exploitable sur « {url} »."

    # La troncature ne porte que sur le corps : l'en-tête et les données
    # structurées (prix…) restent toujours visibles.
    body_limit = max(0, max_chars - len(header) - len(structured_section) - len(TRUNCATION_MARKER) - 2)
    if len(body) > body_limit:
        body = body[:body_limit] + TRUNCATION_MARKER
    return header + body + structured_section


HANDLERS = {
    "ddgs_text_search": _search_text,
    "ddgs_news_search": _search_news,
    "ddgs_image_search": _search_images,
    "ddgs_fetch_url": _fetch_url,
}

# ---------------------------------------------------------------------------
# Serveur
# ---------------------------------------------------------------------------

server = Server(
    name="ddgs",
    version="1.0.0",
    title="DuckDuckGo Search",
    description="Recherche web, actualités et images via DuckDuckGo, plus extraction de texte propre de pages web (gratuit, sans clé API).",
)


async def handle_list_tools(ctx, params: PaginatedRequestParams | None) -> ListToolsResult:
    return ListToolsResult(tools=TOOLS)


async def handle_call_tool(ctx, params: CallToolRequestParams) -> CallToolResult:
    handler = HANDLERS.get(params.name)
    if handler is None:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Outil inconnu : {params.name}")],
            is_error=True,
        )
    try:
        arguments = params.arguments or {}
        result_text = handler(arguments)
        return CallToolResult(content=[TextContent(type="text", text=result_text)])
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Erreur : {e}")],
            is_error=True,
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
