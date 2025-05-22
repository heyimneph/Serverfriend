import discord
import logging
import aiosqlite
import time
import asyncio

from discord.ext import commands, tasks
from discord import app_commands
from core.utils import check_permissions
from discord.ui import Button, View


# ---------------------------------------------------------------------------------------------------------------------
# Database Configuration
# ---------------------------------------------------------------------------------------------------------------------
db_path = './data/databases/serverfriend.db'

# ---------------------------------------------------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------------------------------------------------------
class ActionView(View):
    def __init__(self, user_id, guild_id, cog):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.guild_id = guild_id
        self.cog = cog

    @discord.ui.button(label="Restore User", style=discord.ButtonStyle.success)
    async def restore_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = guild.get_member(self.user_id)
        if user:
            await self.cog.restore_user_roles(guild, user)
            await interaction.response.send_message(f"{user.mention} has been restored.", ephemeral=True)
        else:
            await interaction.response.send_message("User not found.", ephemeral=True)
        # Delete the embed message after the action
        await interaction.message.delete()

    @discord.ui.button(label="Kick User", style=discord.ButtonStyle.danger)
    async def kick_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = guild.get_member(self.user_id)
        if user:
            await guild.kick(user, reason="Spamming")
            await interaction.response.send_message(f"{user.mention} has been kicked.", ephemeral=True)
        else:
            await interaction.response.send_message("User not found.", ephemeral=True)
        # Delete the embed message after the action
        await interaction.message.delete()

    @discord.ui.button(label="Ban User", style=discord.ButtonStyle.danger)
    async def ban_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = guild.get_member(self.user_id)
        if user:
            await guild.ban(user, reason="Spamming")
            await interaction.response.send_message(f"{user.mention} has been banned.", ephemeral=True)
        else:
            await interaction.response.send_message("User not found.", ephemeral=True)
        # Delete the embed message after the action
        await interaction.message.delete()

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.secondary)
    async def dismiss_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Simply delete the embed message
        await interaction.message.delete()


# ---------------------------------------------------------------------------------------------------------------------
# NukeProtectionCog Class
# ---------------------------------------------------------------------------------------------------------------------

class NukeProtectionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.action_log = {}
        self.restricted_users = {}  # Keep track of restricted users to prevent duplicate logging
        self.protection_task.start()

    def cog_unload(self):
        self.protection_task.cancel()

    @tasks.loop(seconds=1)
    async def protection_task(self):
        current_time = time.time()
        to_remove = []

        for key, action_info in self.action_log.items():
            timestamps = action_info["timestamps"]

            # Remove timestamps older than the time frame
            self.action_log[key]["timestamps"] = [
                timestamp for timestamp in timestamps if current_time - timestamp < action_info["time_frame"]
            ]

            # If no timestamps remain, schedule the log for removal
            if not self.action_log[key]["timestamps"]:
                to_remove.append(key)

        # Remove empty logs
        for key in to_remove:
            del self.action_log[key]

    async def log_action(self, user_id, guild_id, action_type, time_frame):
        """Log an action and check if it exceeds the limit."""
        key = (user_id, guild_id, action_type)

        if key not in self.action_log:
            self.action_log[key] = {"timestamps": [], "time_frame": time_frame}

        self.action_log[key]["timestamps"].append(time.time())

        # Fetch the config for the guild
        config = await self.get_protection_config(guild_id)

        # Fallback value to ensure max_allowed is always an integer
        max_allowed = config.get(f"max_{action_type}")
        if max_allowed is None:
            logger.warning(f"Max allowed for action type '{action_type}' is not set. Defaulting to 1.")
            max_allowed = 1  # Set a reasonable default value, such as 1

        if len(self.action_log[key]["timestamps"]) > max_allowed:
            return True  # Action limit exceeded
        return False

    async def get_protection_config(self, guild_id):
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute('SELECT * FROM nuke_protection WHERE guild_id = ?', (guild_id,))
            result = await cursor.fetchone()

            if result:
                return {
                    "enabled": result[1],
                    "max_messages": result[2],
                    "max_bans": result[3],
                    "max_kicks": result[4],
                    "max_channels_deleted": result[5],
                    "max_channels_created": result[6],
                    "max_roles_created": result[7],
                    "time_frame": result[8],
                    "max_channel_updates": result[9],
                    "max_role_updates": result[10]
                }
            return {
                "enabled": True,
                "max_messages": 5,
                "max_bans": 0,
                "max_kicks": 0,
                "max_channels_deleted": 0,
                "max_channels_created": 0,
                "max_roles_created": 0,
                "max_channel_updates": 0,
                "max_role_updates": 0,
                "time_frame": 10
            }

    async def log_event(self, guild_id, user_id, event, extra_info=""):
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute('''
                INSERT INTO nuke_logs (guild_id, user_id, event, extra_info, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (guild_id, user_id, event, extra_info, time.time()))
            await conn.commit()

    async def is_authorized(self, guild_id, user_id):
        """Check if the user is authorized using the check_permissions function."""
        mock_interaction = type('MockInteraction', (),
                                {'guild_id': guild_id, 'user': type('User', (), {'id': user_id})()})()
        return await check_permissions(mock_interaction)

    # -----------------------------------------------------------------------------------------
    # Listener Events
    # -----------------------------------------------------------------------------------------

    # Channel Deletion Protection
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if channel.guild is None:
            return

        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
            user = entry.user

            if user.bot or user.id == channel.guild.owner_id:
                return  # Skip bots and the guild owner

            if not await self.is_authorized(channel.guild.id, user.id):
                exceeded = await self.log_action(user.id, channel.guild.id, "channels_deleted", 10)
                if exceeded:
                    await self.take_preventive_action(channel.guild, user, "channel deletion limit exceeded")

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        await asyncio.sleep(1)  # Add a delay to ensure the correct audit log entry is retrieved
        async for entry in before.guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_update):
            user = entry.user

            # Ensure the action matches the channel being updated and is recent
            if entry.target.id == before.id and (time.time() - entry.created_at.timestamp()) < 5:
                # Debugging logs
                logger.info(f"Audit Log Entry: {entry}, User: {user.name} ({user.id})")

                if not await self.is_authorized(before.guild.id, user.id):
                    exceeded = await self.log_action(user.id, before.guild.id, "channels_updated", 10)
                    if exceeded:
                        await self.take_preventive_action(before.guild, user, "channel update limit exceeded")
                break

    # Role Creation Protection
    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
            user = entry.user

            if not await self.is_authorized(role.guild.id, user.id):
                exceeded = await self.log_action(user.id, role.guild.id, "roles_created", 10)
                if exceeded:
                    await self.take_preventive_action(role.guild, user, "role creation limit exceeded")

    # Role Editing Protection
    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        async for entry in before.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
            user = entry.user

            if not await self.is_authorized(before.guild.id, user.id):
                exceeded = await self.log_action(user.id, before.guild.id, "roles_updated", 10)
                if exceeded:
                    await self.take_preventive_action(before.guild, user, "role update limit exceeded")

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        restricted_role = discord.utils.get(after.guild.roles, name="Restricted")
        if restricted_role in before.roles and restricted_role in after.roles:
            # If the member already had the restricted role and now has additional roles, remove the new roles
            new_roles = [role for role in after.roles if role not in before.roles and role != restricted_role]
            if new_roles:
                try:
                    await after.remove_roles(*new_roles, reason="Restricted role: Cannot add additional roles")
                    logger.info(f"Removed new roles from {after.name} ({after.id}) due to Restricted status.")
                except discord.Forbidden:
                    logger.error(f"Failed to remove new roles from {after.name} ({after.id}) due to Restricted status.")
                except Exception as e:
                    logger.error(f"Error removing roles from {after.name} ({after.id}): {e}")
        elif restricted_role in after.roles and restricted_role not in before.roles:
            # If the restricted role was just added (not already present), remove all other roles
            non_default_roles = [role for role in after.roles if
                                 role != restricted_role and role != after.guild.default_role]
            if non_default_roles:
                try:
                    await after.remove_roles(*non_default_roles,
                                             reason="Restricted role applied: Removing all other roles")
                    logger.info(f"Removed all roles from {after.name} ({after.id}) due to new Restricted status.")
                except discord.Forbidden:
                    logger.error(f"Failed to remove roles from {after.name} ({after.id}) due to new Restricted status.")
                except Exception as e:
                    logger.error(f"Error removing roles from {after.name} ({after.id}): {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        logger.info(f"Member {member.name} ({member.id}) joined the server.")

        if member.bot:
            logger.info(f"Detected that {member.name} is a bot.")
            logger.info(f"All roles in the guild: {[role.name for role in member.guild.roles]}")
            logger.info(f"Roles for {member.name}: {[role.name for role in member.roles]}")

            for role in member.roles:
                if role != member.guild.default_role:
                    original_permissions = role.permissions
                    try:
                        await role.edit(permissions=discord.Permissions.none(),
                                        reason="Stripping permissions from bot role.")
                        logger.info(
                            f"Stripped all permissions from role '{role.name}' for bot {member.name} ({member.id}).")

                        await self.save_bot_original_permissions(member.id, role.id, original_permissions)

                    except discord.Forbidden:
                        logger.error(
                            f"Failed to strip permissions from role '{role.name}' for bot {member.name} ({member.id}) due to insufficient permissions.")
                    except Exception as e:
                        logger.error(
                            f"Error stripping permissions from role '{role.name}' for bot {member.name} ({member.id}): {e}")
            await self.log_bot_quarantine(member)

    async def save_bot_original_permissions(self, bot_id, role_id, permissions):
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute('''
                INSERT INTO bot_roles_permissions (bot_id, role_id, permissions)
                VALUES (?, ?, ?)
                ON CONFLICT(bot_id, role_id) DO UPDATE SET permissions = excluded.permissions
            ''', (bot_id, role_id, permissions.value))  # Store the permissions as an integer value
            await conn.commit()

    async def log_bot_quarantine(self, member):
        logs_channel = discord.utils.get(member.guild.text_channels, name="logs-restrictions")
        if not logs_channel:
            overwrites = {
                member.guild.default_role: discord.PermissionOverwrite(read_messages=False)
            }
            logs_channel = await member.guild.create_text_channel("logs-restrictions", overwrites=overwrites)

        embed = discord.Embed(
            title="Bot Quarantined",
            description=f"The bot {member.mention} has been quarantined.",
            color=discord.Color.red()
        )
        embed.add_field(name="Bot ID", value=f"{member.id}", inline=False)
        embed.add_field(name="Server", value=f"{member.guild.name}", inline=False)
        embed.add_field(name="Server ID", value=f"{member.guild.id}", inline=False)
        embed.set_footer(text=f"{member.name}", icon_url=member.avatar.url)
        embed.timestamp = discord.utils.utcnow()

        view = ActionView(member.id, member.guild.id, self)

        await logs_channel.send(embed=embed, view=view)

    async def restore_user_roles(self, guild, user):
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute('''
                SELECT role_ids FROM restricted_users WHERE user_id = ? AND guild_id = ?
            ''', (user.id, guild.id))
            result = await cursor.fetchone()

        if not result:
            logger.info(f"No stored roles found for user {user.mention}.")
            return

        role_ids = result[0].split(',')

        # Remove the "Restricted" role
        restricted_role = discord.utils.get(guild.roles, name="Restricted")
        if restricted_role in user.roles:
            try:
                await user.remove_roles(restricted_role, reason="Restoring user's original roles")
                logger.info(f"Removed 'Restricted' role from {user.name} ({user.id}).")
            except discord.Forbidden:
                logger.error(
                    f"Failed to remove 'Restricted' role from {user.name} ({user.id}) due to insufficient permissions.")
            except Exception as e:
                logger.error(f"Error removing 'Restricted' role from {user.name} ({user.id}): {e}")

        # Add the original roles back to the user
        roles_to_add = [discord.utils.get(guild.roles, id=int(role_id)) for role_id in role_ids]
        roles_to_add = [role for role in roles_to_add if role is not None]

        if roles_to_add:
            try:
                await user.add_roles(*roles_to_add, reason="Restoring user's original roles")
                logger.info(f"Restored roles for {user.name} ({user.id}).")
            except discord.Forbidden:
                logger.error(f"Failed to restore roles for {user.name} ({user.id}) due to insufficient permissions.")
            except Exception as e:
                logger.error(f"Error restoring roles for {user.name} ({user.id}): {e}")

        # Clean up the database after restoring roles
        async with aiosqlite.connect(db_path) as db:
            await db.execute('DELETE FROM restricted_users WHERE user_id = ? AND guild_id = ?', (user.id, guild.id))
            await db.commit()

    # -----------------------------------------------------------------------------------------
    # Preventive Actions
    # -----------------------------------------------------------------------------------------
    async def take_preventive_action(self, guild, user, reason):
        logger.warning(
            f"Taking preventive action against {user.name} ({user.id}) in guild {guild.name} ({guild.id}) for {reason}.")
        try:
            restricted_role = discord.utils.get(guild.roles, name="Restricted")
            if not restricted_role:
                restricted_role = await guild.create_role(name="Restricted", permissions=discord.Permissions.none())

            # Save the user's current roles (excluding the default role and restricted role)
            role_ids = [role.id for role in user.roles if role != guild.default_role and role != restricted_role]

            # Store the restricted user's roles in the database
            async with aiosqlite.connect(db_path) as db:
                await db.execute('''
                    INSERT INTO restricted_users (user_id, guild_id, role_ids) 
                    VALUES (?, ?, ?) 
                    ON CONFLICT(user_id, guild_id) DO UPDATE SET role_ids = excluded.role_ids                ''', (user.id, guild.id, ','.join(map(str, role_ids))))
                await db.commit()

            # Remove all roles except the default role, and add the restricted role
            await user.remove_roles(*[role for role in user.roles if role != guild.default_role], reason=reason)
            await user.add_roles(restricted_role, reason=reason)

            # Log the restriction with the reason provided
            await self.log_restriction(guild, user, reason)

            # Keep track of restricted users
            self.restricted_users[user.id] = time.time()

        except discord.Forbidden:
            logger.error(f"Failed to restrict {user.name} ({user.id}) in guild {guild.name} ({guild.id}) for {reason}.")
        except Exception as e:
            logger.error(f"Error restricting user {user.name} ({user.id}) in guild {guild.name} ({guild.id}): {e}")

    async def log_restriction(self, guild, user, reason):
        logs_channel = discord.utils.get(guild.text_channels, name="logs-restrictions")
        if not logs_channel:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False)
            }
            logs_channel = await guild.create_text_channel("logs-restrictions", overwrites=overwrites)

        embed = discord.Embed(
            title="User Restricted",
            description=f"{user.mention} has been restricted.",
            color=discord.Color.red()
        )
        embed.add_field(name="User ID", value=f"{user.id}", inline=False)
        embed.add_field(name="Server", value=f"{guild.name}", inline=False)
        embed.add_field(name="Server ID", value=f"{guild.id}", inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text=f"{user.name}", icon_url=user.avatar.url)
        embed.timestamp = discord.utils.utcnow()

        view = ActionView(user.id, guild.id, self)

        await logs_channel.send(embed=embed, view=view)

    # -----------------------------------------------------------------------------------------
    # Antinuke Commands
    # -----------------------------------------------------------------------------------------
    @app_commands.command(name="enable_protection", description="Enable nuke protection for the server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def enable_protection(self, interaction: discord.Interaction):
        """Enable nuke protection."""
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute('SELECT guild_id FROM nuke_protection WHERE guild_id = ?',
                                        (interaction.guild.id,))
            result = await cursor.fetchone()

            if not result:
                await conn.execute('''
                    INSERT INTO nuke_protection (guild_id, enabled, max_messages, max_bans, max_kicks, max_channels_deleted, max_channels_created, max_roles_created, max_channel_updates, max_role_updates, time_frame)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (interaction.guild.id, True, 5, 0, 0, 0, 0, 0, 0, 0, 10))
            else:
                await conn.execute('''
                    UPDATE nuke_protection
                    SET enabled = ?
                    WHERE guild_id = ?
                ''', (True, interaction.guild.id))

            await conn.commit()

        await interaction.response.send_message("Nuke protection has been enabled.", ephemeral=True)

    @app_commands.command(name="disable_protection", description="Disable nuke protection for the server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def disable_protection(self, interaction: discord.Interaction):
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                'INSERT INTO nuke_protection (guild_id, enabled) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET enabled = excluded.enabled',
                (interaction.guild.id, False))
            await conn.commit()
        await interaction.response.send_message("Nuke protection has been disabled.", ephemeral=True)

    @app_commands.command(name="lockdown", description="Activate emergency lockdown mode for the server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def lockdown(self, interaction: discord.Interaction):
        guild = interaction.guild
        for role in guild.roles:
            if role != guild.default_role:
                await role.edit(permissions=discord.Permissions.none())
        await interaction.response.send_message("The server is now in lockdown mode.", ephemeral=True)
        await self.log_event(interaction.guild.id, interaction.user.id, "lockdown", "Server lockdown activated.")

    @app_commands.command(name="unlock", description="Deactivate emergency lockdown mode for the server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def unlock(self, interaction: discord.Interaction):
        guild = interaction.guild
        for role in guild.roles:
            await role.edit(permissions=discord.Permissions.all())
        await interaction.response.send_message("The server is now out of lockdown mode.", ephemeral=True)
        await self.log_event(interaction.guild.id, interaction.user.id, "unlock", "Server lockdown deactivated.")

    # -----------------------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------------
    #                               Testing Commands
    # -----------------------------------------------------------------------------------------
    # -----------------------------------------------------------------------------------------

    @app_commands.command(name="create_test_channels_roles",
                          description="Create 10 test channels and 10 test roles for testing.")
    @app_commands.checks.has_permissions(administrator=True)
    async def create_test_channels_roles(self, interaction: discord.Interaction):
        guild = interaction.guild

        await interaction.response.defer(ephemeral=True)

        for i in range(10):
            role_name = f"TestRole-{i + 1}"
            await guild.create_role(name=role_name)

        for i in range(10):
            channel_name = f"test-channel-{i + 1}"
            await guild.create_text_channel(name=channel_name)

        await self.log_event(interaction.guild.id, interaction.user.id, "test_channels_roles_created",
                             f"Created 10 test channels and 10 test roles.")
        await interaction.followup.send("10 test channels and 10 test roles have been created.", ephemeral=True)

    @app_commands.command(name="delete_all_test_channels_roles", description="Delete all test channels and test roles.")
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_all_test_channels_roles(self, interaction: discord.Interaction):
        guild = interaction.guild

        await interaction.response.defer(ephemeral=True)

        channels_to_delete = [channel for channel in guild.channels if channel.name.startswith("test-channel-")]
        for channel in channels_to_delete:
            await channel.delete()

        roles_to_delete = [role for role in guild.roles if role.name.startswith("TestRole-")]
        for role in roles_to_delete:
            await role.delete()

        await self.log_event(interaction.guild.id, interaction.user.id, "delete_all_test_channels_roles",
                             f"Deleted {len(channels_to_delete)} test channels and {len(roles_to_delete)} test roles.")
        await interaction.followup.send(
            f"Deleted {len(channels_to_delete)} test channels and {len(roles_to_delete)} test roles.", ephemeral=True)

# ----------------------------------------------------------------------------------------------------------------------
# Setup Function
# ----------------------------------------------------------------------------------------------------------------------

async def setup(bot):
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS nuke_protection (
            guild_id INTEGER PRIMARY KEY,
            enabled BOOLEAN DEFAULT 1,
            max_messages INTEGER DEFAULT 5,
            max_bans INTEGER DEFAULT 0,
            max_kicks INTEGER DEFAULT 0,
            max_channels_deleted INTEGER DEFAULT 0,
            max_channels_created INTEGER DEFAULT 0,
            max_roles_created INTEGER DEFAULT 0,
            time_frame INTEGER DEFAULT 10,
            max_channel_updates INTEGER DEFAULT 0,
            max_role_updates INTEGER DEFAULT 0
        )
        ''')


        await conn.execute('''
        CREATE TABLE IF NOT EXISTS nuke_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            event TEXT,
            extra_info TEXT,
            timestamp INTEGER
        )
        ''')

        await conn.execute('''
        CREATE TABLE IF NOT EXISTS restricted_users (
            user_id INTEGER,
            guild_id INTEGER,
            role_ids TEXT,
            PRIMARY KEY (user_id, guild_id)
        )
        ''')

        await conn.execute('''
        CREATE TABLE IF NOT EXISTS bot_roles_permissions (
            bot_id INTEGER,
            role_id INTEGER,
            permissions INTEGER,
            PRIMARY KEY (bot_id, role_id)
        )
        ''')

        await conn.commit()
    await bot.add_cog(NukeProtectionCog(bot))

