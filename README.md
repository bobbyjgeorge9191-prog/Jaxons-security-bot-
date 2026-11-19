# Jaxon's Security Bot

A Python Discord security/moderation bot with anti-spam, link filtering, join-raid alerts, audit-log-based anti-nuke alerts, SQLite incident history, trusted roles, and manual lockdown commands.

## Requirements
- Python 3.10+
- A Discord application and bot token
- Enable **Server Members Intent**, **Message Content Intent**, and **Moderation Events** in the Discord Developer Portal.
- Invite with OAuth2 scopes `bot` and `applications.commands`.

Suggested bot permissions: View Channels, Send Messages, Embed Links, Read Message History, Manage Messages, Moderate Members, Manage Channels, and View Audit Log. Keep the bot role above members it may timeout.

## Run locally
1. Install dependencies: `pip install -r requirements.txt`
2. Set `DISCORD_TOKEN` as an environment variable. Never commit your token or a real `.env` file.
3. Run: `python bot.py`

## Render background worker
- Build command: `pip install -r requirements.txt`
- Start command: `python bot.py`
- Set `DISCORD_TOKEN` as a secret environment variable.
- Set `DATABASE_PATH=/var/data/jaxons_security.sqlite3`.
- Attach a persistent disk mounted at `/var/data` to preserve SQLite history.
- Use an always-on Background Worker plan for 24/7 operation; free web services may sleep.

## First setup in Discord
1. Run `/setlog` and choose a private staff-only channel.
2. Run `/trustedrole` to add a trusted staff role.
3. Run `/security` to review settings.
4. Use `/lockdown` only for emergencies; `/unlockdown` clears the default role's send-permission overrides.

## Safety notes
This is a defensive moderation aid, not a guarantee. Anti-nuke checks rely on audit logs and may not catch every action. It does not restore deleted channels or roles and has no web dashboard. Test in a private server and review permissions before enabling it in a large community.
