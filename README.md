# 🦆 mcp-ddgs

Serveur MCP pour la recherche web via **DuckDuckGo** — gratuit, anonyme, sans clé API.

Donne aux agents IA (Goose, Claude Desktop, Cursor, Continue, etc.) la capacité de **chercher sur le web** en temps réel et **d'extraire le contenu propre d'une page** (sans publicités ni navigation).

## Outils

| Outil | Description |
|---|---|
| `ddgs_text_search` | Recherche web classique — titre, URL, extrait |
| `ddgs_news_search` | Actualités récentes |
| `ddgs_image_search` | Recherche d'images — URLs + descriptions |
| `ddgs_fetch_url_article` | Texte éditorial principal (articles, blogs, actualités) — sans données produit/prix |
| `ddgs_fetch_url_full` | Tout le texte visible + données structurées (prix/produit) — pages produit/e-commerce, et en cas de doute |

## Installation rapide

### Goose

```yaml
# ~/.config/goose/config.yaml
extensions:
  ddgs:
    enabled: true
    type: stdio
    name: DDGS
    description: Recherche web DuckDuckGo
    cmd: uvx
    args:
      - --from
      - git+https://github.com/Llamatron2112/mcp-ddgs.git
      - mcp-ddgs
    timeout: 300
```

### Claude Desktop

```json
{
  "mcpServers": {
    "ddgs": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Llamatron2112/mcp-ddgs.git", "mcp-ddgs"]
    }
  }
}
```

## Développement local

```bash
git clone https://github.com/Llamatron2112/mcp-ddgs.git
cd mcp-ddgs
uv sync
uv run mcp-ddgs
```

## Licence

MIT
