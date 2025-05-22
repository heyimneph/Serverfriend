import discord
import logging
import aiosqlite
import os
import inspect

from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
from datetime import datetime

from core.utils import log_command_usage, check_permissions
from cogs.customisation import get_embed_colour

# ---------------------------------------------------------------------------------------------------------------------
# Database Configuration
# ---------------------------------------------------------------------------------------------------------------------

db_path = './data/databases/serverfriend.db'

# ---------------------------------------------------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------------------------------------------------
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------------------------------------------------
# Utility Cog Class
# ---------------------------------------------------------------------------------------------------------------------
class UtilityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot_start_time = datetime.utcnow()

    async def has_required_permissions(self, interaction, command):
        if interaction.user.guild_permissions.administrator:
            return True

        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute('''
                SELECT can_use_commands FROM permissions WHERE guild_id = ? AND user_id = ?
            ''', (interaction.guild.id, interaction.user.id))
            permission = await cursor.fetchone()
            if permission and permission[0]:
                return True

        if "Admin" in command.description or "Owner" in command.description:
            return False

        for check in command.checks:
            try:
                if inspect.iscoroutinefunction(check):
                    result = await check(interaction)
                else:
                    result = check(interaction)
                if not result:
                    return False
            except Exception as e:
                logger.error(f"Permission check failed: {e}")
                return False

        return True

    # ---------------------------------------------------------------------------------------------------------------------

    @app_commands.command(description="Admin: Authorize a user to use the bot.")
    @app_commands.describe(user="The user to authorize")
    @app_commands.checks.has_permissions(administrator=True)
    async def authorise(self, interaction: discord.Interaction, user: discord.User):
        ALLOWED_USER_IDS = {111941993629806592}

        if interaction.user.id not in ALLOWED_USER_IDS:
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True
            )
            return

        try:
            async with aiosqlite.connect(db_path) as conn:
                await conn.execute('''
                            INSERT INTO permissions (guild_id, user_id, can_use_commands) VALUES (?, ?, 1)
                            ON CONFLICT(guild_id, user_id) DO UPDATE SET can_use_commands = 1
                        ''', (interaction.guild.id, user.id))
                await conn.commit()
            await interaction.response.send_message(f"{user.display_name} has been authorized.", ephemeral=True)

        except Exception as e:
            logger.error(f"Failed to authorise user: {e}")
            await interaction.response.send_message(f"Failed to authorise user: {e}",
                                                    ephemeral=True)

        finally:
            await log_command_usage(self.bot, interaction)

    @app_commands.command(description="Admin: Revoke a user's authorization to use the bot.")
    @app_commands.describe(user="The user to unauthorize")
    @app_commands.checks.has_permissions(administrator=True)
    async def unauthorise(self, interaction: discord.Interaction, user: discord.User):
        try:
            async with aiosqlite.connect(db_path) as conn:
                await conn.execute('''
                    UPDATE permissions SET can_use_commands = 0 WHERE guild_id = ? AND user_id = ?
                ''', (interaction.guild.id, user.id))
                await conn.commit()
            await interaction.response.send_message(f"{user.display_name} has been unauthorized.", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to unauthorise user: {e}")
            await interaction.response.send_message(f"Failed to unauthorise user: {e}",
                                                    ephemeral=True)
        finally:
            await log_command_usage(self.bot, interaction)


# ---------------------------------------------------------------------------------------------------------------------
# Setup Function
# ---------------------------------------------------------------------------------------------------------------------
async def setup(bot):
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS blacklist (
                user_id INTEGER PRIMARY KEY
            )
        ''')
        await conn.execute('''
                CREATE TABLE IF NOT EXISTS permissions (
                    guild_id INTEGER,
                    user_id INTEGER,
                    can_use_commands BOOLEAN DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
            ''')

        await conn.commit()
    await bot.add_cog(UtilityCog(bot))



