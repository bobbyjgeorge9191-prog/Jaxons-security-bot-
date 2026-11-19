import os
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands
from dotenv import load_dotenv

from database import init_db, get_setting, set_setting, add_incident, recent_incidents

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("BOT_PREFIX", "!")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing. Set it in your hosting provider's environment variables.")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True
intents.moderation = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

message_hits = defaultdict(deque)
join_hits = defaultdict(deque)
action_hits = defaultdict(deque)
seen_audit_entries = set()


def trusted(guild, member):
    if member.id == guild.owner_id or member.guild_permissions.administrator:
        return True
    role_ids = set(get_setting(guild.id, "trusted_role_ids", []))
    return any(role.id in role_ids for role in getattr(member, "roles", []))


async def log_event(guild, title, detail):
    channel_id = get_setting(guild.id, "log_channel_id", None)
    if channel_id:
        channel = guild.get_channel(int(channel_id))
        if channel:
            try:
                await channel.send(embed=discord.Embed(
                    title=title, description=detail[:4000],
                    color=discord.Color.orange(), timestamp=discord.utils.utcnow()
                ))
            except discord.HTTPException:
                pass
    add_incident(guild.id, title, detail)


async def timeout_member(member, reason):
    if member.bot or trusted(member.guild, member):
        return False
    try:
        await member.timeout(discord.utils.utcnow() + timedelta(minutes=10), reason=reason)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Online as {bot.user}; slash commands synced.")


@bot.event
async def on_message(message):
    if message.guild and not message.author.bot and isinstance(message.author, discord.Member):
        cfg = get_setting(message.guild.id, "config", {})
        if cfg.get("anti_spam", True) and not trusted(message.guild, message.author):
            now = time.time()
            q = message_hits[(message.guild.id, message.author.id)]
            q.append(now)
            while q and now - q[0] > 8:
                q.popleft()
            if len(q) >= 7:
                acted = await timeout_member(message.author, "Jaxon's Security Bot: spam protection")
                await log_event(message.guild, "Anti-spam alert",
                                f"{message.author} ({message.author.id}) reached the rapid-message threshold. Timeout applied: {acted}.")
                q.clear()
        if cfg.get("anti_links", True) and not trusted(message.guild, message.author):
            body = message.content.lower()
            if any(x in body for x in ("discord.gg/", "discord.com/invite/", "http://", "https://")):
                try:
                    await message.delete()
                    await log_event(message.guild, "Link removed",
                                    f"Removed a link from {message.author} ({message.author.id}).")
                except discord.HTTPException:
                    pass
    await bot.process_commands(message)


@bot.event
async def on_member_join(member):
    if not get_setting(member.guild.id, "config", {}).get("anti_raid", True):
        return
    now = time.time()
    q = join_hits[member.guild.id]
    q.append(now)
    while q and now - q[0] > 20:
        q.popleft()
    if len(q) == 8:
        await log_event(member.guild, "Possible join raid",
                        "8 or more members joined within 20 seconds. Review the member list and consider /lockdown.")


async def check_nuke(guild, action_name, limit):
    if len(seen_audit_entries) > 5000:
        seen_audit_entries.clear()
    try:
        entries = [entry async for entry in guild.audit_logs(limit=10)]
    except (discord.Forbidden, discord.HTTPException):
        return
    now = time.time()
    for entry in entries:
        if now - entry.created_at.timestamp() > 20 or entry.id in seen_audit_entries:
            continue
        seen_audit_entries.add(entry.id)
        actor = entry.user
        if not isinstance(actor, discord.Member) or trusted(guild, actor):
            continue
        q = action_hits[(guild.id, actor.id, action_name)]
        q.append(now)
        while q and now - q[0] > 30:
            q.popleft()
        if len(q) >= limit:
            acted = await timeout_member(actor, f"Anti-nuke: repeated {action_name}")
            await log_event(guild, "Anti-nuke alert",
                            f"{actor} ({actor.id}) triggered repeated {action_name}. Timeout applied: {acted}. Review audit logs.")
            q.clear()
            break


@bot.event
async def on_guild_channel_delete(channel):
    await check_nuke(channel.guild, "channel deletions", 3)


@bot.event
async def on_guild_role_delete(role):
    await check_nuke(role.guild, "role deletions", 3)


@bot.event
async def on_member_ban(guild, user):
    await check_nuke(guild, "member bans", 4)


@bot.tree.command(name="setlog", description="Set the channel for security logs.")
async def setlog(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("You need Manage Server permission.", ephemeral=True)
    set_setting(interaction.guild_id, "log_channel_id", channel.id)
    await interaction.response.send_message(f"Security logs will be sent to {channel.mention}.", ephemeral=True)


@bot.tree.command(name="trustedrole", description="Add or remove a trusted role.")
async def trustedrole(interaction: discord.Interaction, role: discord.Role, trusted_value: bool = True):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("You need Manage Server permission.", ephemeral=True)
    ids = set(get_setting(interaction.guild_id, "trusted_role_ids", []))
    if trusted_value:
        ids.add(role.id)
    else:
        ids.discard(role.id)
    set_setting(interaction.guild_id, "trusted_role_ids", sorted(ids))
    await interaction.response.send_message(f"{role.mention} trusted: {trusted_value}.", ephemeral=True)


@bot.tree.command(name="security", description="Show current security settings.")
async def security(interaction: discord.Interaction):
    cfg = get_setting(interaction.guild_id, "config", {})
    await interaction.response.send_message(
        f"**Jaxon's Security Bot**\nAnti-spam: {cfg.get('anti_spam', True)}\n"
        f"Anti-links: {cfg.get('anti_links', True)}\nAnti-raid: {cfg.get('anti_raid', True)}\n"
        f"Logs: {'configured' if get_setting(interaction.guild_id, 'log_channel_id') else 'not configured'}",
        ephemeral=True
    )


@bot.tree.command(name="lockdown", description="Lock sending in all text channels.")
async def lockdown(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        return await interaction.response.send_message("You need Manage Channels permission.", ephemeral=True)
    changed = 0
    for channel in interaction.guild.text_channels:
        try:
            await channel.set_permissions(interaction.guild.default_role, send_messages=False, reason="Security lockdown")
            changed += 1
        except discord.Forbidden:
            pass
    await interaction.response.send_message(f"Lockdown applied to {changed} text channels.", ephemeral=True)
    await log_event(interaction.guild, "Manual lockdown", f"Started by {interaction.user}.")


@bot.tree.command(name="unlockdown", description="Clear lockdown send-permission overrides.")
async def unlockdown(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        return await interaction.response.send_message("You need Manage Channels permission.", ephemeral=True)
    changed = 0
    for channel in interaction.guild.text_channels:
        try:
            await channel.set_permissions(interaction.guild.default_role, send_messages=None, reason="End security lockdown")
            changed += 1
        except discord.Forbidden:
            pass
    await interaction.response.send_message(f"Unlockdown cleared in {changed} text channels.", ephemeral=True)
    await log_event(interaction.guild, "Manual unlockdown", f"Started by {interaction.user}.")


@bot.tree.command(name="incidents", description="Show the latest security incidents.")
async def incidents(interaction: discord.Interaction):
    rows = recent_incidents(interaction.guild_id, 5)
    if not rows:
        return await interaction.response.send_message("No incidents recorded yet.", ephemeral=True)
    body = "\n".join(f"• **{title}** — {detail[:180]}" for title, detail, _ in rows)
    await interaction.response.send_message(body[:1900], ephemeral=True)


@bot.tree.command(name="help-security", description="Show security bot commands.")
async def help_security(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**Commands**\n/setlog #channel\n/trustedrole @role trusted_value:true/false\n"
        "/security\n/lockdown\n/unlockdown\n/incidents\n/help-security",
        ephemeral=True
    )


init_db()
bot.run(TOKEN)
