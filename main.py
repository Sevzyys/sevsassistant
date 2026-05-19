"""
Assistant AIO - Server Utility Bot
The ultimate all-in-one system for complete Discord server control.
"""

import discord
from discord.ext import commands
from discord import app_commands
import random
import datetime


# ─── Bot Setup ────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# In-memory stores (replace with a DB for production)
blacklisted_users: set[int] = set()
muted_users: dict[int, datetime.datetime] = {}
claimed_tickets: dict[int, int] = {}          # channel_id -> staff_user_id
locked_channels: set[int] = set()
autorole_config: dict[int, int] = {}          # guild_id -> role_id
welcome_config: dict[int, dict] = {}          # guild_id -> {channel_id, enabled}
saved_embeds: dict[str, dict] = {}            # name -> embed data
giveaways: dict[int, dict] = {}              # message_id -> giveaway data
staff_stats: dict[int, int] = {}             # user_id -> tickets closed
verification_config: dict[int, dict] = {}    # guild_id -> config


# ─── Events ───────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"⚡ Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"❌ Sync error: {e}")


@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild

    # Auto-role
    if guild.id in autorole_config:
        role = guild.get_role(autorole_config[guild.id])
        bot_member = guild.get_member(bot.user.id)
        if role and bot_member:
            # Bot's highest role must be above the target role
            if bot_member.top_role > role and bot_member.guild_permissions.manage_roles:
                try:
                    await member.add_roles(role, reason="Auto-role on join")
                except discord.Forbidden:
                    print(f"⚠️  Auto-role: missing permissions to assign '{role.name}' in '{guild.name}'")
                except discord.HTTPException as e:
                    print(f"⚠️  Auto-role: HTTP error assigning role — {e}")
            else:
                print(
                    f"⚠️  Auto-role skipped in '{guild.name}': bot's top role "
                    f"('{bot_member.top_role.name}') must be ranked above '{role.name}' "
                    f"and bot needs Manage Roles permission."
                )

    # Welcome message
    cfg = welcome_config.get(guild.id)
    if cfg and cfg.get("enabled"):
        channel = guild.get_channel(cfg["channel_id"])
        if channel:
            embed = discord.Embed(
                title=f"Welcome, {member.display_name}! 👋",
                description=f"You are member **#{guild.member_count}** of **{guild.name}**.",
                color=0x5865F2,
                timestamp=datetime.datetime.now(datetime.UTC),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def staff_embed(title: str, description: str, color: int = 0x5865F2) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.timestamp = datetime.datetime.now(datetime.UTC)
    return embed


def is_blacklisted(user_id: int) -> bool:
    return user_id in blacklisted_users


async def check_blacklist(interaction: discord.Interaction) -> bool:
    if is_blacklisted(interaction.user.id):
        await interaction.response.send_message(
            "❌ You are blacklisted from using this bot.", ephemeral=True
        )
        return False
    return True


# ─── MODERATION ───────────────────────────────────────────────────────────────

@bot.tree.command(name="ban", description="Permanently ban a member")
@app_commands.describe(member="Member to ban", reason="Reason for the ban")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not await check_blacklist(interaction):
        return
    await member.ban(reason=reason)
    await interaction.response.send_message(
        embed=staff_embed("🔨 Member Banned", f"{member.mention} has been banned.\n**Reason:** {reason}", 0xED4245)
    )


@bot.tree.command(name="kick", description="Remove a member from the server")
@app_commands.describe(member="Member to kick", reason="Reason for the kick")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not await check_blacklist(interaction):
        return
    await member.kick(reason=reason)
    await interaction.response.send_message(
        embed=staff_embed("👟 Member Kicked", f"{member.mention} has been kicked.\n**Reason:** {reason}", 0xFEE75C)
    )


@bot.tree.command(name="mute", description="Temporarily mute a member")
@app_commands.describe(member="Member to mute", duration="Duration in minutes")
@app_commands.checks.has_permissions(moderate_members=True)
async def mute(interaction: discord.Interaction, member: discord.Member, duration: int = 10):
    if not await check_blacklist(interaction):
        return
    until = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=duration)
    await member.timeout(datetime.timedelta(minutes=duration), reason="Muted by staff")
    muted_users[member.id] = until
    await interaction.response.send_message(
        embed=staff_embed("🔇 Member Muted", f"{member.mention} muted for **{duration} minute(s)**.", 0xFEE75C)
    )


@bot.tree.command(name="blacklist", description="Blacklist a user from using bot systems")
@app_commands.describe(user="User to blacklist")
@app_commands.checks.has_permissions(manage_guild=True)
async def blacklist(interaction: discord.Interaction, user: discord.User):
    blacklisted_users.add(user.id)
    await interaction.response.send_message(
        embed=staff_embed("🚫 User Blacklisted", f"{user.mention} (`{user.id}`) has been blacklisted.", 0xED4245)
    )


@bot.tree.command(name="unblacklist", description="Remove a user from the blacklist")
@app_commands.describe(user="User to remove from the blacklist")
@app_commands.checks.has_permissions(manage_guild=True)
async def unblacklist(interaction: discord.Interaction, user: discord.User):
    # NOTE: intentionally skips check_blacklist so staff can always run this
    if user.id not in blacklisted_users:
        await interaction.response.send_message(
            embed=staff_embed("⚠️ Not Blacklisted", f"{user.mention} is not currently blacklisted.", 0xFEE75C),
            ephemeral=True,
        )
        return
    blacklisted_users.discard(user.id)
    await interaction.response.send_message(
        embed=staff_embed("✅ User Unblacklisted", f"{user.mention} has been removed from the blacklist.", 0x57F287)
    )


@bot.tree.command(name="purge", description="Bulk delete messages in a channel")
@app_commands.describe(amount="Number of messages to delete (max 100)")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int = 10):
    if not await check_blacklist(interaction):
        return
    amount = min(amount, 100)
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(
        embed=staff_embed("🗑️ Purge Complete", f"Deleted **{len(deleted)}** message(s).", 0x5865F2),
        ephemeral=True,
    )


@bot.tree.command(name="addrole", description="Give a role to a user")
@app_commands.describe(member="Target member", role="Role to assign")
@app_commands.checks.has_permissions(manage_roles=True)
async def addrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not await check_blacklist(interaction):
        return
    await member.add_roles(role)
    await interaction.response.send_message(
        embed=staff_embed("✅ Role Added", f"{role.mention} added to {member.mention}.", 0x57F287)
    )


@bot.tree.command(name="removestaff", description="Remove a staff role from a user")
@app_commands.describe(member="Target member", role="Staff role to remove")
@app_commands.checks.has_permissions(manage_roles=True)
async def removestaff(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not await check_blacklist(interaction):
        return
    await member.remove_roles(role)
    await interaction.response.send_message(
        embed=staff_embed("🔴 Staff Role Removed", f"{role.mention} removed from {member.mention}.", 0xED4245)
    )


# ─── CHANNEL CONTROLS ─────────────────────────────────────────────────────────

@bot.tree.command(name="lock", description="Lock a channel to prevent messages")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    if not await check_blacklist(interaction):
        return
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    locked_channels.add(interaction.channel.id)
    await interaction.response.send_message(
        embed=staff_embed("🔒 Channel Locked", f"{interaction.channel.mention} has been locked.", 0xED4245)
    )


@bot.tree.command(name="unlock", description="Unlock a previously locked channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    if not await check_blacklist(interaction):
        return
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = True
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    locked_channels.discard(interaction.channel.id)
    await interaction.response.send_message(
        embed=staff_embed("🔓 Channel Unlocked", f"{interaction.channel.mention} has been unlocked.", 0x57F287)
    )


@bot.tree.command(name="rename", description="Rename a channel or ticket")
@app_commands.describe(name="New channel name")
@app_commands.checks.has_permissions(manage_channels=True)
async def rename(interaction: discord.Interaction, name: str):
    if not await check_blacklist(interaction):
        return
    old_name = interaction.channel.name
    await interaction.channel.edit(name=name)
    await interaction.response.send_message(
        embed=staff_embed("✏️ Channel Renamed", f"`#{old_name}` → `#{name}`", 0x5865F2)
    )


# ─── TICKET SYSTEM ────────────────────────────────────────────────────────────

@bot.tree.command(name="panel", description="Create or send a ticket panel")
@app_commands.checks.has_permissions(manage_channels=True)
async def panel(interaction: discord.Interaction):
    if not await check_blacklist(interaction):
        return
    embed = discord.Embed(
        title="🎫 Support Tickets",
        description="Click the button below to open a support ticket.\nOur staff will assist you shortly.",
        color=0x5865F2,
    )
    embed.set_footer(text="Assistant AIO • Ticket System")

    class TicketButton(discord.ui.View):
        @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, emoji="🎫")
        async def open_ticket(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
            overwrites = {
                btn_interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                btn_interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            }
            ticket_channel = await btn_interaction.guild.create_text_channel(
                name=f"ticket-{btn_interaction.user.name}",
                overwrites=overwrites,
                reason=f"Ticket opened by {btn_interaction.user}",
            )
            await ticket_channel.send(
                embed=staff_embed("🎫 Ticket Opened", f"Welcome {btn_interaction.user.mention}! Staff will be with you shortly.")
            )
            await btn_interaction.response.send_message(
                f"✅ Your ticket has been created: {ticket_channel.mention}", ephemeral=True
            )

    await interaction.response.send_message(embed=embed, view=TicketButton())


@bot.tree.command(name="claim", description="Claim a ticket for handling")
async def claim(interaction: discord.Interaction):
    if not await check_blacklist(interaction):
        return
    claimed_tickets[interaction.channel.id] = interaction.user.id
    staff_stats[interaction.user.id] = staff_stats.get(interaction.user.id, 0)
    await interaction.response.send_message(
        embed=staff_embed("✋ Ticket Claimed", f"This ticket has been claimed by {interaction.user.mention}.", 0x57F287)
    )


@bot.tree.command(name="unclaim", description="Unassign a claimed ticket")
async def unclaim(interaction: discord.Interaction):
    if not await check_blacklist(interaction):
        return
    claimed_tickets.pop(interaction.channel.id, None)
    await interaction.response.send_message(
        embed=staff_embed("🔄 Ticket Unclaimed", "This ticket is now available for staff to claim.", 0xFEE75C)
    )


@bot.tree.command(name="add", description="Add a user to a ticket")
@app_commands.describe(member="Member to add to this ticket")
async def add(interaction: discord.Interaction, member: discord.Member):
    if not await check_blacklist(interaction):
        return
    await interaction.channel.set_permissions(member, read_messages=True, send_messages=True)
    await interaction.response.send_message(
        embed=staff_embed("➕ User Added", f"{member.mention} has been added to this ticket.", 0x57F287)
    )


@bot.tree.command(name="ticketlookup", description="Search and view ticket information")
@app_commands.describe(channel="Ticket channel to look up")
async def ticketlookup(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await check_blacklist(interaction):
        return
    claimer_id = claimed_tickets.get(channel.id)
    claimer = f"<@{claimer_id}>" if claimer_id else "Unclaimed"
    locked = "Yes" if channel.id in locked_channels else "No"
    embed = staff_embed("🔍 Ticket Lookup", f"**Channel:** {channel.mention}\n**Claimed by:** {claimer}\n**Locked:** {locked}")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ─── AUTO-ROLE & WELCOME ──────────────────────────────────────────────────────

@bot.tree.command(name="autorole-set", description="Set an automatic role for new users")
@app_commands.describe(role="Role to assign to new members")
@app_commands.checks.has_permissions(manage_guild=True)
async def autorole_set(interaction: discord.Interaction, role: discord.Role):
    autorole_config[interaction.guild.id] = role.id
    await interaction.response.send_message(
        embed=staff_embed("✅ Auto-role Set", f"New members will receive {role.mention} on join.", 0x57F287)
    )


@bot.tree.command(name="autorole-show", description="View current autorole settings")
async def autorole_show(interaction: discord.Interaction):
    role_id = autorole_config.get(interaction.guild.id)
    if role_id:
        role = interaction.guild.get_role(role_id)
        desc = f"Current auto-role: {role.mention if role else f'ID `{role_id}` (deleted)'}"
    else:
        desc = "No auto-role configured."
    await interaction.response.send_message(embed=staff_embed("⚙️ Auto-role Config", desc), ephemeral=True)


@bot.tree.command(name="autorole-remove", description="Remove autorole configuration")
@app_commands.checks.has_permissions(manage_guild=True)
async def autorole_remove(interaction: discord.Interaction):
    autorole_config.pop(interaction.guild.id, None)
    await interaction.response.send_message(
        embed=staff_embed("🗑️ Auto-role Removed", "Auto-role configuration has been cleared.", 0xFEE75C)
    )


@bot.tree.command(name="welcome-enable", description="Enable the welcome system")
@app_commands.checks.has_permissions(manage_guild=True)
async def welcome_enable(interaction: discord.Interaction):
    cfg = welcome_config.setdefault(interaction.guild.id, {"channel_id": None, "enabled": False})
    cfg["enabled"] = True
    await interaction.response.send_message(
        embed=staff_embed("✅ Welcome System Enabled", "New members will now receive a welcome message.", 0x57F287)
    )


@bot.tree.command(name="welcome-setchannel", description="Set the welcome message channel")
@app_commands.describe(channel="Channel for welcome messages")
@app_commands.checks.has_permissions(manage_guild=True)
async def welcome_setchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = welcome_config.setdefault(interaction.guild.id, {"channel_id": None, "enabled": True})
    cfg["channel_id"] = channel.id
    await interaction.response.send_message(
        embed=staff_embed("📨 Welcome Channel Set", f"Welcome messages will be sent to {channel.mention}.", 0x57F287)
    )


# ─── EMBED BUILDER ────────────────────────────────────────────────────────────

@bot.tree.command(name="create-embed", description="Create a new custom embed")
@app_commands.describe(title="Embed title", description="Embed body text", color="Hex color e.g. 5865F2")
@app_commands.checks.has_permissions(manage_messages=True)
async def create_embed(interaction: discord.Interaction, title: str, description: str, color: str = "5865F2"):
    try:
        hex_color = int(color.lstrip("#"), 16)
    except ValueError:
        hex_color = 0x5865F2
    embed = discord.Embed(title=title, description=description, color=hex_color)
    embed.set_footer(text=f"Created by {interaction.user}")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="save-embed", description="Save an embed for later use")
@app_commands.describe(name="Name/key for this embed", title="Embed title", description="Embed body text")
@app_commands.checks.has_permissions(manage_messages=True)
async def save_embed(interaction: discord.Interaction, name: str, title: str, description: str):
    saved_embeds[name] = {"title": title, "description": description}
    await interaction.response.send_message(
        embed=staff_embed("💾 Embed Saved", f"Embed **{name}** saved successfully.", 0x57F287), ephemeral=True
    )


@bot.tree.command(name="list-embeds", description="Show all saved embeds")
async def list_embeds(interaction: discord.Interaction):
    if not saved_embeds:
        desc = "No saved embeds yet."
    else:
        desc = "\n".join(f"• `{k}` — {v['title']}" for k, v in saved_embeds.items())
    await interaction.response.send_message(embed=staff_embed("📋 Saved Embeds", desc), ephemeral=True)


@bot.tree.command(name="send-embed", description="Send a saved embed to a channel")
@app_commands.describe(name="Embed name", channel="Channel to send to")
@app_commands.checks.has_permissions(manage_messages=True)
async def send_embed(interaction: discord.Interaction, name: str, channel: discord.TextChannel):
    data = saved_embeds.get(name)
    if not data:
        await interaction.response.send_message(f"❌ No embed named `{name}` found.", ephemeral=True)
        return
    embed = discord.Embed(title=data["title"], description=data["description"], color=0x5865F2)
    await channel.send(embed=embed)
    await interaction.response.send_message(
        embed=staff_embed("📤 Embed Sent", f"Embed `{name}` sent to {channel.mention}.", 0x57F287), ephemeral=True
    )


# ─── GIVEAWAYS ────────────────────────────────────────────────────────────────

@bot.tree.command(name="giveaway-start", description="Start a new giveaway")
@app_commands.describe(prize="What are you giving away?", duration="Duration in minutes", winners="Number of winners")
@app_commands.checks.has_permissions(manage_guild=True)
async def giveaway_start(interaction: discord.Interaction, prize: str, duration: int = 60, winners: int = 1):
    if not await check_blacklist(interaction):
        return
    ends_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=duration)
    embed = discord.Embed(
        title="🎉 Giveaway!",
        description=f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** <t:{int(ends_at.timestamp())}:R>\n\nReact with 🎉 to enter!",
        color=0xF47FFF,
    )
    embed.set_footer(text=f"Hosted by {interaction.user}")
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    await msg.add_reaction("🎉")
    giveaways[msg.id] = {
        "prize": prize, "winners": winners, "ends_at": ends_at,
        "channel_id": interaction.channel.id, "host_id": interaction.user.id, "active": True,
    }


@bot.tree.command(name="giveaway-end", description="End an active giveaway")
@app_commands.describe(message_id="Message ID of the giveaway")
@app_commands.checks.has_permissions(manage_guild=True)
async def giveaway_end(interaction: discord.Interaction, message_id: str):
    gw = giveaways.get(int(message_id))
    if not gw or not gw["active"]:
        await interaction.response.send_message("❌ No active giveaway with that ID.", ephemeral=True)
        return
    gw["active"] = False
    channel = bot.get_channel(gw["channel_id"])
    try:
        msg = await channel.fetch_message(int(message_id))
        reaction = discord.utils.get(msg.reactions, emoji="🎉")
        users = [u async for u in reaction.users() if not u.bot]
        if not users:
            await interaction.response.send_message(
                embed=staff_embed("🎉 Giveaway Ended", f"No valid entries for **{gw['prize']}**.", 0xF47FFF)
            )
            return
        selected = random.sample(users, min(gw["winners"], len(users)))
        mentions = ", ".join(u.mention for u in selected)
        await interaction.response.send_message(
            embed=staff_embed("🎉 Giveaway Ended!", f"**Prize:** {gw['prize']}\n**Winner(s):** {mentions}", 0xF47FFF)
        )
        gw["last_winners"] = [u.id for u in selected]
    except Exception as e:
        await interaction.response.send_message(f"❌ Error ending giveaway: {e}", ephemeral=True)


@bot.tree.command(name="giveaway-reroll", description="Reroll a giveaway winner")
@app_commands.describe(message_id="Message ID of the giveaway")
@app_commands.checks.has_permissions(manage_guild=True)
async def giveaway_reroll(interaction: discord.Interaction, message_id: str):
    gw = giveaways.get(int(message_id))
    if not gw:
        await interaction.response.send_message("❌ Giveaway not found.", ephemeral=True)
        return
    channel = bot.get_channel(gw["channel_id"])
    try:
        msg = await channel.fetch_message(int(message_id))
        reaction = discord.utils.get(msg.reactions, emoji="🎉")
        users = [u async for u in reaction.users() if not u.bot]
        winner = random.choice(users)
        await interaction.response.send_message(
            embed=staff_embed("🔄 Giveaway Rerolled", f"New winner for **{gw['prize']}**: {winner.mention}!", 0xF47FFF)
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


@bot.tree.command(name="giveaway-list", description="List all active giveaways")
async def giveaway_list(interaction: discord.Interaction):
    active = {mid: g for mid, g in giveaways.items() if g["active"]}
    if not active:
        await interaction.response.send_message(
            embed=staff_embed("🎉 Giveaways", "No active giveaways right now."), ephemeral=True
        )
        return
    desc = "\n".join(
        f"• **{g['prize']}** — `{mid}` — <t:{int(g['ends_at'].timestamp())}:R>"
        for mid, g in active.items()
    )
    await interaction.response.send_message(embed=staff_embed("🎉 Active Giveaways", desc), ephemeral=True)


@bot.tree.command(name="giveaway-info", description="View details about a giveaway")
@app_commands.describe(message_id="Message ID of the giveaway")
async def giveaway_info(interaction: discord.Interaction, message_id: str):
    gw = giveaways.get(int(message_id))
    if not gw:
        await interaction.response.send_message("❌ Giveaway not found.", ephemeral=True)
        return
    status = "✅ Active" if gw["active"] else "🔴 Ended"
    desc = (
        f"**Prize:** {gw['prize']}\n"
        f"**Winners:** {gw['winners']}\n"
        f"**Ends:** <t:{int(gw['ends_at'].timestamp())}:R>\n"
        f"**Host:** <@{gw['host_id']}>\n"
        f"**Status:** {status}"
    )
    await interaction.response.send_message(embed=staff_embed("🎉 Giveaway Info", desc), ephemeral=True)


# ─── STATS & LEADERBOARD ──────────────────────────────────────────────────────

@bot.tree.command(name="stats", description="View server or bot statistics")
async def stats(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title="📊 Server Statistics", color=0x5865F2, timestamp=datetime.datetime.now(datetime.UTC))
    embed.add_field(name="Members", value=guild.member_count, inline=True)
    embed.add_field(name="Channels", value=len(guild.channels), inline=True)
    embed.add_field(name="Roles", value=len(guild.roles), inline=True)
    embed.add_field(name="Active Giveaways", value=sum(1 for g in giveaways.values() if g["active"]), inline=True)
    embed.add_field(name="Blacklisted Users", value=len(blacklisted_users), inline=True)
    embed.add_field(name="Saved Embeds", value=len(saved_embeds), inline=True)
    embed.set_footer(text="Assistant AIO")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="leaderboard", description="View top staff or activity rankings")
async def leaderboard(interaction: discord.Interaction):
    if not staff_stats:
        await interaction.response.send_message(
            embed=staff_embed("🏆 Leaderboard", "No staff activity recorded yet."), ephemeral=True
        )
        return
    sorted_staff = sorted(staff_stats.items(), key=lambda x: x[1], reverse=True)[:10]
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    desc = "\n".join(
        f"{medals[i]} <@{uid}> — **{count}** tickets handled"
        for i, (uid, count) in enumerate(sorted_staff)
    )
    await interaction.response.send_message(embed=staff_embed("🏆 Staff Leaderboard", desc))


# ─── UTILITY ──────────────────────────────────────────────────────────────────

@bot.tree.command(name="calc", description="Perform quick calculations")
@app_commands.describe(expression="Math expression to evaluate e.g. 2 + 2 * 10")
async def calc(interaction: discord.Interaction, expression: str):
    try:
        allowed_chars = set("0123456789+-*/(). ")
        if not all(c in allowed_chars for c in expression):
            raise ValueError("Invalid characters in expression.")
        result = eval(expression, {"__builtins__": {}})  # noqa: S307
        await interaction.response.send_message(
            embed=staff_embed("🧮 Calculator", f"`{expression}` = **{result}**", 0x5865F2)
        )
    except Exception:
        await interaction.response.send_message("❌ Invalid expression.", ephemeral=True)


@bot.tree.command(name="alert", description="Send an alert or notification")
@app_commands.describe(channel="Target channel", message="Alert message to send")
@app_commands.checks.has_permissions(manage_messages=True)
async def alert(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    embed = discord.Embed(
        title="⚠️ Server Alert",
        description=message,
        color=0xFEE75C,
        timestamp=datetime.datetime.now(datetime.UTC),
    )
    embed.set_footer(text=f"Sent by {interaction.user}")
    await channel.send(embed=embed)
    await interaction.response.send_message(
        embed=staff_embed("📣 Alert Sent", f"Alert sent to {channel.mention}.", 0x57F287), ephemeral=True
    )


@bot.tree.command(name="payment", description="Display payment information")
@app_commands.describe(method="Payment method (e.g. PayPal, CashApp)", details="Payment details or link")
@app_commands.checks.has_permissions(manage_guild=True)
async def payment(interaction: discord.Interaction, method: str, details: str):
    embed = discord.Embed(title="💳 Payment Information", color=0x57F287)
    embed.add_field(name="Method", value=method, inline=True)
    embed.add_field(name="Details", value=details, inline=True)
    embed.set_footer(text="Assistant AIO • Payment System")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ss", description="Take or trigger a system snapshot/log")
@app_commands.checks.has_permissions(manage_guild=True)
async def ss(interaction: discord.Interaction):
    guild = interaction.guild
    snapshot = (
        f"**Guild:** {guild.name} (`{guild.id}`)\n"
        f"**Members:** {guild.member_count}\n"
        f"**Channels:** {len(guild.channels)}\n"
        f"**Blacklisted:** {len(blacklisted_users)}\n"
        f"**Locked Channels:** {len(locked_channels)}\n"
        f"**Active Giveaways:** {sum(1 for g in giveaways.values() if g['active'])}\n"
        f"**Saved Embeds:** {len(saved_embeds)}\n"
        f"**Snapshot at:** <t:{int(datetime.datetime.now(datetime.UTC).timestamp())}:F>"
    )
    await interaction.response.send_message(
        embed=staff_embed("📸 System Snapshot", snapshot, 0x5865F2), ephemeral=True
    )


@bot.tree.command(name="setup-verification", description="Configure verification system for new members")
@app_commands.describe(role="Role to assign after verification", channel="Channel to post verification prompt")
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_verification(interaction: discord.Interaction, role: discord.Role, channel: discord.TextChannel):
    verification_config[interaction.guild.id] = {"role_id": role.id, "channel_id": channel.id}

    class VerifyView(discord.ui.View):
        @discord.ui.button(label="Verify", style=discord.ButtonStyle.success, emoji="✅")
        async def verify(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
            member_role = btn_interaction.guild.get_role(role.id)
            if member_role:
                await btn_interaction.user.add_roles(member_role, reason="Verified")
                await btn_interaction.response.send_message("✅ You have been verified!", ephemeral=True)

    embed = discord.Embed(
        title="🔒 Member Verification",
        description="Click the button below to verify yourself and gain access to the server.",
        color=0x57F287,
    )
    await channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message(
        embed=staff_embed("✅ Verification Setup", f"Verification panel sent to {channel.mention}.", 0x57F287),
        ephemeral=True,
    )


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        raise ValueError("Set the DISCORD_BOT_TOKEN environment variable before running.")
    bot.run(TOKEN)