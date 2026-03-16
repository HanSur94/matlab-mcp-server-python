# How to Publish the Wiki

GitHub requires the first wiki page to be created via the web UI before the wiki git repo becomes available.

## One-Time Setup

1. Go to https://github.com/HanSur94/matlab-mcp-server-python/wiki
2. Click "Create the first page"
3. Add any placeholder text and click "Save Page"
4. Now run these commands to push all wiki pages:

```bash
cd /tmp
git clone https://github.com/HanSur94/matlab-mcp-server-python.wiki.git matlab-mcp-wiki
cd matlab-mcp-wiki

# Copy all wiki pages
cp /path/to/matlab-mcp-server-python/wiki/*.md .
# Remove this setup file
rm SETUP_WIKI.md

git add -A
git commit -m "Add comprehensive wiki pages"
git push origin master
```

## Wiki Pages Included

- **Home.md** — Main page with navigation
- **Installation.md** — Prerequisites, setup, agent integration
- **Configuration.md** — Full YAML config reference
- **MCP-Tools-Reference.md** — All 20 tools with parameters
- **Custom-Tools.md** — How to expose .m functions
- **Examples.md** — Ready-to-run MATLAB examples
- **Architecture.md** — System design and data flow
- **Async-Jobs.md** — Long-running jobs and progress
- **Security.md** — Blocklist, isolation, SSE protection
- **Troubleshooting.md** — Common issues and fixes
- **FAQ.md** — Frequently asked questions
