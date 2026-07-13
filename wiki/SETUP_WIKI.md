# Maintaining the Wiki

> This file is a **maintainer note**, not a published wiki page. Do not copy it into the live wiki.

The published GitHub wiki — <https://github.com/HanSur94/matlab-mcp-server-python/wiki> — is **hand-maintained** from the Markdown files in this `wiki/` folder.

The previous AI auto-generation pipeline (`.github/workflows/docs.yml` → `HanSur94/wiki-gen-action`) was **removed**; the wiki no longer regenerates itself on merge. Edit the pages here and publish them explicitly.

## Publishing changes

GitHub wikis live in a **separate git repo** (`…​.wiki.git`). To publish the current pages:

```bash
git clone https://github.com/HanSur94/matlab-mcp-server-python.wiki.git /tmp/mm-wiki
cd /tmp/mm-wiki
cp /path/to/matlab-mcp-server-python/wiki/*.md .
rm -f SETUP_WIKI.md            # keep this maintainer note out of the live wiki
git add -A
git commit -m "docs: update wiki"
git push origin master
```

The one-time bootstrap (creating the first wiki page via the web UI so the `.wiki.git` repo exists) is already done.

## Pages

`Home` · `Installation` · `Configuration` · `MCP-Tools-Reference` · `Custom-Tools` · `Examples` · `Architecture` · `Async-Jobs` · `Security` · `Troubleshooting` · `FAQ`
