# Democracy and Rule of Law board embed

Shows the public Trello board of the Democracy and Rule of Law Collective on humanityhub.org as a tabbed browser, styled with the site's own design tokens.

**How it works:** every Monday a GitHub Action reads the board through the Trello API, fetches each link's title, summary and event date from the source page, and rebuilds `dorl-embed.html`. The website loads that file through jsDelivr with a Shortcoder snippet. No iframe, so the site's CSP is not involved.

## Files

| File | Purpose |
|---|---|
| `build.py` | Fetches the board, enriches links, renders the embed |
| `template.html` | Layout and styling (the tabbed browser) |
| `overrides.json` | Manual title or summary fixes for individual cards |
| `data/metadata.json` | Cache of fetched page metadata (created automatically) |
| `.github/workflows/update.yml` | Weekly schedule, Mondays 05:17 UTC, plus a manual button |
| `shortcoder-snippet.html` | Paste into Shortcoder as `dorl-board` |

## One-off setup

1. **Create the repo** `thehaguehumanityhub/dorl-board` (public, so jsDelivr can serve it) and upload these files.
2. **Get a Trello API key and token** (recommended, but optional: without them the script falls back to the board's public JSON export)
   - Go to trello.com/power-ups/admin, create a Power-Up (any name, e.g. "THHH website"), and generate an API key.
   - On the same page, follow the link to generate a token. For a read-only token that does not expire, open:
     `https://trello.com/1/authorize?expiration=never&scope=read&response_type=token&key=YOUR_KEY`
3. **Add both as repo secrets**: Settings > Secrets and variables > Actions > New repository secret: `TRELLO_KEY` and `TRELLO_TOKEN`.
4. **Run it once**: Actions tab > "Update board embed" > Run workflow. Check that `dorl-embed.html` appears in the repo.
5. **Shortcoder**: create a shortcode named `dorl-board`, paste the contents of `shortcoder-snippet.html`, and insert `[sc name="dorl-board"]` on the page.

## Maintenance

- **Force an update** (after a big board change): Actions > Run workflow.
- **Fix a bad title**: some sites (LinkedIn, some news sites) block metadata. Add the card's short code to `overrides.json`, e.g. `"CS1qzpDD": {"title": "Real event title"}`, and run the workflow.
- **Include or exclude a list**: edit `EXCLUDE_LISTS` in `build.py`. "Collective's Shared Resources" is excluded because it holds the Signal invite and the Google Drive link.
- **Restyle**: edit `template.html`. It reads the site's `--strl-*` CSS variables, so site-wide colour changes carry over automatically.
- **Local test**: `python build.py --board-json export.json --offline`
