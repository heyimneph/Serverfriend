import discord
import aiosqlite
import os
from discord import app_commands
from discord.ext import commands
from config import client, perform_sync
from core.utils import log_command_usage

# Ensure the database directory exists
os.makedirs('./data/databases', exist_ok=True)

# Path to the SQLite database
db_path = './data/databases/serverfriend.db'

# ---------------------------------------------------------------------------------------------------------------------
# Admin Cog
# ---------------------------------------------------------------------------------------------------------------------
class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def check_or_create_admin_log_channel(self, guild):
        log_channel_name = "logs"
        log_channel = discord.utils.get(guild.text_channels, name=log_channel_name)

        if not log_channel:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True),
            }
            # Find role(s) with admin permission
            for role in guild.roles:
                if role.permissions.administrator:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True)

            # Create the channel with the specified overwrites
            log_channel = await guild.create_text_channel(log_channel_name, overwrites=overwrites)

        async with aiosqlite.connect(db_path) as conn:
            await conn.execute('''
            INSERT INTO config (guild_id, log_channel_id) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET log_channel_id = excluded.log_channel_id
            ''', (guild.id, log_channel.id))
            await conn.commit()

        return log_channel

# ---------------------------------------------------------------------------------------------------------------------
# Admin Commands
# ---------------------------------------------------------------------------------------------------------------------
    @app_commands.command(description="Run the setup for 'ServerFriend'")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            await self.check_or_create_admin_log_channel(interaction.guild)
            await interaction.followup.send("`Success: Setup has been completed`")
        except Exception as e:
            await interaction.followup.send("`Error: Something Unexpected Happened`")
        finally:
            await log_command_usage(self.bot, interaction)

    @app_commands.command(description="Reset a specific table in the database")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_table(self, interaction: discord.Interaction, table_name: str):
        await interaction.response.defer()
        try:
            # Connect to the database
            async with aiosqlite.connect(db_path) as conn:
                # Fetch the schema for the specified table
                cursor = await conn.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name = ?",
                                            (table_name,))
                schema = await cursor.fetchone()
                if not schema:
                    await interaction.followup.send(f'`Error: No table found with name {table_name}`')
                    return

                # Drop the specified table
                await conn.execute(f'DROP TABLE IF EXISTS {table_name}')
                # Recreate the table using the fetched schema
                await conn.execute(schema[0])
                await conn.commit()

            await interaction.followup.send(f'`Success: {table_name} table has been reset`')
        except Exception as e:
            await interaction.followup.send(f'`Error: Failed to reset {table_name} table. {str(e)}`')


    @app_commands.command(description="Delete a specific table from the database")
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_table(self, interaction: discord.Interaction, table_name: str):
        await interaction.response.defer()
        try:
            # Connect to the database
            async with aiosqlite.connect(db_path) as conn:
                # Check if the table exists before attempting to delete
                cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                                            (table_name,))
                exists = await cursor.fetchone()
                if not exists:
                    await interaction.followup.send(f'`Error: No table found with name {table_name}`')
                    return

                # Delete the specified table
                await conn.execute(f'DROP TABLE IF EXISTS {table_name}')
                await conn.commit()

            await interaction.followup.send(f'`Success: {table_name} table has been deleted`')
        except Exception as e:
            await interaction.followup.send(f'`Error: Failed to delete {table_name} table. {str(e)}`')

# ---------------------------------------------------------------------------------------------------------------------
# Owner Commands
# ---------------------------------------------------------------------------------------------------------------------
    @app_commands.command(description="Load a Cog")
    @app_commands.checks.has_permissions(administrator=True)
    async def load(self, interaction: discord.Interaction, extension: str):
        try:
            await interaction.response.defer()
            await client.load_extension(f'cogs.{extension}')
            await interaction.followup.send(f'`Success: Loaded {extension}`')
            await perform_sync()
        except Exception as e:
            await interaction.followup.send(f'`Error: Failed to load {extension}`')
        finally:
            await log_command_usage(self.bot, interaction)

    @app_commands.command(description="Unload a Cog")
    @app_commands.checks.has_permissions(administrator=True)
    async def unload(self, interaction: discord.Interaction, extension: str):
        try:
            await interaction.response.defer()
            await client.unload_extension(f'cogs.{extension}')
            await interaction.followup.send(f'`Success: Unloaded {extension}`')
        except Exception as e:
            await interaction.followup.send(f'`Error: Failed to unload {extension}`')
        finally:
            await log_command_usage(self.bot, interaction)

    @app_commands.command(description="Reload a Cog")
    @app_commands.checks.has_permissions(administrator=True)
    async def reload(self, interaction: discord.Interaction, extension: str):
        try:
            await interaction.response.defer()
            await client.unload_extension(f'cogs.{extension}')
            await client.load_extension(f'cogs.{extension}')
            await interaction.followup.send(f'Reloaded {extension}.')
            await perform_sync()
        except Exception as e:
            await interaction.followup.send(f'`Error: Failed to reload {extension}`')
        finally:
            await log_command_usage(self.bot, interaction)

# ---------------------------------------------------------------------------------------------------------------------
# Setup Function
# ---------------------------------------------------------------------------------------------------------------------
async def setup(bot):
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS config (
            guild_id INTEGER PRIMARY KEY,
            log_channel_id INTEGER
        )
        ''')
        await conn.commit()
    await bot.add_cog(AdminCog(bot))
