import discord
import logging
import aiosqlite
import os
from discord import app_commands
from discord.ext import commands
from core.utils import log_command_usage

# Ensure the database directory exists
os.makedirs('./data/databases', exist_ok=True)

# Path to the SQLite database
db_path = './data/databases/serverfriend.db'

# ---------------------------------------------------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------------------------------------------------

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------------------------------
# Customisation Functions
# ---------------------------------------------------------------------------------------------------------------------

async def get_embed_colour(conn):
    async with conn.execute('SELECT value FROM customisation WHERE type = ?', ("embed_color",)) as cursor:
        row = await cursor.fetchone()
        if row:
            return int(row[0], 16)  # Assuming the color is stored as a hex string
        return 0x3498db

async def get_bio_settings(conn):
    async with conn.execute('SELECT value FROM customisation WHERE type = ?', ("activity_type",)) as cursor:
        activity_type_doc = await cursor.fetchone()
    async with conn.execute('SELECT value FROM customisation WHERE type = ?', ("bio",)) as cursor:
        bio_doc = await cursor.fetchone()
    if activity_type_doc and bio_doc:
        return activity_type_doc[0], bio_doc[0]
    return None, None

# ---------------------------------------------------------------------------------------------------------------------
# Customisation Cog
# ---------------------------------------------------------------------------------------------------------------------

class CustomisationCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(description="Admin: Change the bot's avatar.")
    @app_commands.checks.has_permissions(administrator=True)
    async def change_avatar(self, interaction: discord.Interaction, url: str):
        try:
            async with self.bot.http._HTTPClient__session.get(url) as response:
                data = await response.read()
                await self.bot.user.edit(avatar=data)

            await interaction.response.send_message("`Success: Avatar Changed!`")

        except Exception as e:
            await interaction.followup.send("`Error: Something Unexpected Happened`")
        finally:
            await log_command_usage(self.bot, interaction)

    @app_commands.command(description="Admin: Set Embed Color")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_embed_colour(self, interaction: discord.Interaction, colour: str):
        async with aiosqlite.connect(db_path) as conn:
            try:
                # Convert the color string to a valid discord.Color object
                try:
                    if colour.startswith("#"):
                        color = colour[1:]  # Strip the '#' character if present

                    color_obj = discord.Color(int(color, 16))  # Convert the hexadecimal string to an integer
                except ValueError:
                    await interaction.response.send_message("`Error: Invalid color format! Please provide a valid hexadecimal color value.`", ephemeral=True)
                    return

                # Store the color value in the database
                async with conn.execute('SELECT value FROM customisation WHERE type = ?', ("embed_color",)) as cursor:
                    embed_color_doc = await cursor.fetchone()
                if not embed_color_doc:
                    await conn.execute('INSERT INTO customisation (type, value) VALUES (?, ?)', ("embed_color", color))
                else:
                    await conn.execute('UPDATE customisation SET value = ? WHERE type = ?', (color, "embed_color"))
                await conn.commit()

                # Send a confirmation message
                await interaction.response.send_message(f"`Success: Embed color has been set to #{color}!`", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"`Error: {e}`")
                logger.error(f"An error occurred: {str(e)}")
            finally:
                await log_command_usage(self.bot, interaction)

    @app_commands.command(description="Admin: Change Bot's Bio")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_bio(self, interaction: discord.Interaction, activity_type: str, bio: str):
        async with aiosqlite.connect(db_path) as conn:
            try:
                if activity_type.lower() == "playing":
                    activity = discord.Game(name=bio)
                elif activity_type.lower() == "listening":
                    activity = discord.Activity(type=discord.ActivityType.listening, name=bio)
                elif activity_type.lower() == "watching":
                    activity = discord.Activity(type=discord.ActivityType.watching, name=bio)
                else:
                    await interaction.response.send_message(
                        "`Error: Invalid activity type! Choose from playing, listening, or watching.`", ephemeral=True)
                    return

                await self.bot.change_presence(activity=activity)

                # Store the bio settings in the database
                await conn.execute('INSERT INTO customisation (type, value) VALUES (?, ?) '
                                   'ON CONFLICT(type) DO UPDATE SET value=excluded.value', ("activity_type", activity_type))
                await conn.execute('INSERT INTO customisation (type, value) VALUES (?, ?) '
                                   'ON CONFLICT(type) DO UPDATE SET value=excluded.value', ("bio", bio))
                await conn.commit()

                # Send a confirmation message
                await interaction.response.send_message(f"`Success: Bot's activity has been set to {activity_type} '{bio}'`", ephemeral=True)

            except Exception as e:
                await interaction.followup.send(f"`Error: {e}`")
                logger.error(f"An error occurred: {str(e)}")
            finally:
                await log_command_usage(self.bot, interaction)

    @set_bio.autocomplete("activity_type")
    async def activity_type_autocomplete(self, interaction: discord.Interaction, current: str):
        activity_types = ["playing", "listening", "watching"]
        return [app_commands.Choice(name=atype, value=atype) for atype in activity_types if current.lower() in atype.lower()]

# ---------------------------------------------------------------------------------------------------------------------
# Setup Function
# ---------------------------------------------------------------------------------------------------------------------

async def setup(bot):
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS customisation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT UNIQUE,
            value TEXT
        )
        ''')
        await conn.commit()
    await bot.add_cog(CustomisationCog(bot))