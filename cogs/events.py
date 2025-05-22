import discord
import logging
import aiohttp
import aiosqlite
import os
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# Ensure the database directory exists
os.makedirs('./data/databases', exist_ok=True)

# Path to the SQLite database
db_path = './data/databases/serverfriend.db'

# Default Settings
DEFAULT_WELCOME_MESSAGE = "Welcome to the server, {member}!"
DEFAULT_TEXT_OVERLAY = "'{member}' has just joined the server"
DEFAULT_BACKGROUND_COLOUR = "#EDDCFE"
DEFAULT_BACKGROUND_IMAGE = None
DEFAULT_AVATAR_RING_COLOUR = "#C891F9"
DEFAULT_TEXT_COLOR = "#000000"

# ---------------------------------------------------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------------------------------
# Event Class
# ---------------------------------------------------------------------------------------------------------------------
class EventCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def create_welcome_image(self, member, guild_id):
        # Fetch the avatar
        avatar_url = str(member.avatar.url) if member.avatar else member.default_avatar.url
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as resp:
                if resp.status != 200:
                    return None
                avatar_data = BytesIO(await resp.read())

        # Fetch customization from the database
        async with aiosqlite.connect(db_path) as conn:
            async with conn.execute(
                    'SELECT background_colour, background_image, avatar_ring_colour, text_overlay, text_color FROM event_config WHERE guild_id = ?',
                    (guild_id,)) as cursor:
                result = await cursor.fetchone()

        if not result:
            # Use default settings if no specific settings are found
            background_colour = DEFAULT_BACKGROUND_COLOUR
            background_image_url = DEFAULT_BACKGROUND_IMAGE
            avatar_ring_colour = DEFAULT_AVATAR_RING_COLOUR
            text_overlay = DEFAULT_TEXT_OVERLAY
            text_color = '#000000'
        else:
            background_colour, background_image_url, avatar_ring_colour, text_overlay, text_color = result

        default_background_size = (500, 250)
        # Create the background
        if background_image_url:
            async with aiohttp.ClientSession() as session:
                async with session.get(background_image_url) as resp:
                    if resp.status != 200:
                        return None
                    background_data = BytesIO(await resp.read())
            background = Image.open(background_data).resize(default_background_size, Image.LANCZOS)
        else:
            background = Image.new('RGB', default_background_size, color=background_colour)

        initial_size = 400
        border_size = 20
        final_size = 100

        # Load and resize the avatar
        avatar_image = Image.open(avatar_data).resize((initial_size, initial_size)).convert("RGBA")

        # Create a circular mask for the avatar
        mask = Image.new('L', (initial_size, initial_size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, initial_size, initial_size), fill=255)
        avatar_image.putalpha(mask)

        # Create a larger image for the border
        bordered_size = initial_size + border_size * 2
        bordered_image = Image.new('RGBA', (bordered_size, bordered_size), avatar_ring_colour)
        avatar_position = (border_size, border_size)
        bordered_image.paste(avatar_image, avatar_position, avatar_image)

        border_mask = Image.new('L', (bordered_size, bordered_size), 0)
        ImageDraw.Draw(border_mask).ellipse((0, 0, bordered_size, bordered_size), fill=255)
        bordered_image.putalpha(border_mask)

        final_image = bordered_image.resize((final_size, final_size), Image.LANCZOS)

        # Position the avatar in the center of the background
        background_position = ((background.width - final_size) // 2, 50)
        background.paste(final_image, background_position, final_image)

        # Add the welcome text
        draw = ImageDraw.Draw(background)
        font_path = "data/welcome/Roboto-Regular.ttf"
        font = ImageFont.truetype(font_path, 24)
        formatted_text = text_overlay.replace("{member}", member.display_name)  # Replace the placeholder

        text_bbox = draw.textbbox((0, 0), formatted_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_position = ((background.width - text_width) // 2, background_position[1] + final_size + 10)
        draw.text(text_position, formatted_text, fill=text_color, font=font)  # Use the custom text color

        # Save to a BytesIO object
        final_buffer = BytesIO()
        background.save(final_buffer, "PNG")
        final_buffer.seek(0)

        return final_buffer

    # ---------------------------------------------------------------------------------------------------------------------
    # Event Commands
    # ---------------------------------------------------------------------------------------------------------------------
    @app_commands.command(description="Set the Default Role and Channel for new members")
    @commands.has_permissions(administrator=True)
    async def welcome_set_defaults(self, interaction: discord.Interaction, channel: discord.TextChannel,
                                   role: discord.Role = None):
        guild_id = interaction.guild.id

        async with aiosqlite.connect(db_path) as conn:
            await conn.execute('''
            INSERT INTO event_config (guild_id, default_role_id, default_channel_id) VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET default_role_id = excluded.default_role_id, default_channel_id = excluded.default_channel_id
            ''', (guild_id, role.id if role else None, channel.id))
            await conn.commit()

        response_message = f"Success: Default Channel set: {channel.mention}."
        if role:
            response_message += f"\nDefault Role set: {role.name}."
        else:
            response_message += "\nNo default role set."

        await interaction.response.send_message(f"`{response_message}`", ephemeral=True)

    @app_commands.command(description="Set the Welcome Message for New Members")
    @commands.has_permissions(administrator=True)
    async def welcome_set_message(self, interaction: discord.Interaction, message: str):
        guild_id = interaction.guild.id

        async with aiosqlite.connect(db_path) as conn:
            await conn.execute('''
            INSERT INTO event_config (guild_id, welcome_message) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET welcome_message = excluded.welcome_message
            ''', (guild_id, message))
            await conn.commit()

        await interaction.response.send_message(
            f"`Success: Welcome message set to: '{message}'`", ephemeral=True)

    @app_commands.command(description="Set the Background Colour for the Welcome Image")
    @commands.has_permissions(administrator=True)
    async def welcome_background_colour(self, interaction: discord.Interaction, colour: str):
        guild_id = interaction.guild.id

        async with aiosqlite.connect(db_path) as conn:
            await conn.execute('''
            INSERT INTO event_config (guild_id, background_colour) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET background_colour = excluded.background_colour
            ''', (guild_id, colour))
            await conn.commit()

        await interaction.response.send_message(
            f"`Success: Background colour set to: {colour}`", ephemeral=True)

    @app_commands.command(description="Set the Background Image for the Welcome Image (500x250)")
    @commands.has_permissions(administrator=True)
    async def welcome_background_image(self, interaction: discord.Interaction, url: str):
        guild_id = interaction.guild.id

        async with aiosqlite.connect(db_path) as conn:
            await conn.execute('''
            INSERT INTO event_config (guild_id, background_image) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET background_image = excluded.background_image
            ''', (guild_id, url))
            await conn.commit()

        await interaction.response.send_message(
            f"`Success: Background image set to: {url}`", ephemeral=True)

    @app_commands.command(description="Set the Ring Colour for the Welcome Image")
    @commands.has_permissions(administrator=True)
    async def welcome_avatar_ring_colour(self, interaction: discord.Interaction, colour: str):
        guild_id = interaction.guild.id

        async with aiosqlite.connect(db_path) as conn:
            await conn.execute('''
            INSERT INTO event_config (guild_id, avatar_ring_colour) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET avatar_ring_colour = excluded.avatar_ring_colour
            ''', (guild_id, colour))
            await conn.commit()

        await interaction.response.send_message(
            f"`Success: Avatar ring colour set to: {colour}`",
            ephemeral=True)

    @app_commands.command(description="Set the Text Overlay for the Welcome Image")
    @commands.has_permissions(administrator=True)
    async def welcome_text_overlay(self, interaction: discord.Interaction, text: str):
        guild_id = interaction.guild.id
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute('''
            INSERT INTO event_config (guild_id, text_overlay) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET text_overlay = excluded.text_overlay
            ''', (guild_id, text))
            await conn.commit()

        await interaction.response.send_message(
            f"`Success: Text overlay set to: '{text}'`", ephemeral=True)

    @app_commands.command(description="Set the Text Colour for the Welcome Image Overlay")
    @commands.has_permissions(administrator=True)
    async def welcome_text_color(self, interaction: discord.Interaction, color: str):
        guild_id = interaction.guild.id
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute('''
            INSERT INTO event_config (guild_id, text_color) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET text_color = excluded.text_color
            ''', (guild_id, color))
            await conn.commit()

        await interaction.response.send_message(f"`Success: Text color set to: {color}`", ephemeral=True)

    @app_commands.command(description="Reset to default Welcome Message and Settings")
    @commands.has_permissions(administrator=True)
    async def welcome_reset(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id

        async with aiosqlite.connect(db_path) as conn:
            # Updating the command to reset all customizable fields including text_overlay and text_color
            await conn.execute('''
            UPDATE event_config SET
                welcome_message = ?,
                background_colour = ?,
                background_image = ?,
                avatar_ring_colour = ?,
                text_overlay = ?,
                text_color = ?  
            WHERE guild_id = ?
            ''', (
                DEFAULT_WELCOME_MESSAGE,
                DEFAULT_BACKGROUND_COLOUR,
                DEFAULT_BACKGROUND_IMAGE,
                DEFAULT_AVATAR_RING_COLOUR,
                DEFAULT_TEXT_OVERLAY,
                DEFAULT_TEXT_COLOR,
                guild_id))
            await conn.commit()

        # Sending confirmation message to the interaction initiator
        await interaction.response.send_message(
            "`Success: All Welcome Event settings have been RESET to default values`", ephemeral=True)

    # ---------------------------------------------------------------------------------------------------------------------
    # Event Listeners
    # ---------------------------------------------------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member):
        server = member.guild
        if member.bot:
            return  # Skip if the member is a bot

        async with aiosqlite.connect(db_path) as conn:
            async with conn.execute(
                    'SELECT default_role_id, default_channel_id, welcome_message FROM event_config WHERE guild_id = ?',
                    (server.id,)) as cursor:
                config = await cursor.fetchone()

        if not config:
            logger.warning(f"No configuration found for server: {server.name}")
            return

        role_id, channel_id, welcome_message = config

        # Try to add role if specified
        if role_id:
            role = server.get_role(role_id)
            if role:
                await member.add_roles(role)
            else:
                logger.warning(f"Could not find the default role: {role_id} in server: {server.name}")

        # Try to find a suitable channel or use defaults
        if channel_id:
            channel = server.get_channel(channel_id)
        else:
            # Find a default channel if none specified
            channel = discord.utils.find(lambda x: x.name in ['welcome', 'general'], server.text_channels)
            if not channel:
                channel = next((x for x in server.text_channels if x.permissions_for(server.me).send_messages), None)

        if not channel:
            logger.warning(f"Could not find a suitable channel to send the welcome message in server: {server.name}")
            return

        # Create and send welcome image
        welcome_image_buffer = await self.create_welcome_image(member, server.id)  # Corrected function call
        if welcome_image_buffer:
            welcome_message_formatted = welcome_message.replace("{member}",
                                                                member.mention) if welcome_message else f"Welcome to the server, {member.mention}!"
            await channel.send(welcome_message_formatted, file=discord.File(welcome_image_buffer, "welcome_image.png"))

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f"{self.bot.user} has connected to Discord!")
        for guild in self.bot.guilds:
            async with aiosqlite.connect(db_path) as conn:
                # Check if the guild is already configured
                cursor = await conn.execute('SELECT 1 FROM event_config WHERE guild_id = ?', (guild.id,))
                if not await cursor.fetchone():
                    # Insert default configuration if not exists
                    await conn.execute('''
                        INSERT INTO event_config (guild_id, welcome_message, background_colour, background_image, avatar_ring_colour)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (guild.id, DEFAULT_WELCOME_MESSAGE, DEFAULT_BACKGROUND_COLOUR, DEFAULT_BACKGROUND_IMAGE, DEFAULT_AVATAR_RING_COLOUR))
                    await conn.commit()
                await cursor.close()
        logger.info("Checked and updated database entries for all guilds.")

# ---------------------------------------------------------------------------------------------------------------------
# Setup Function
# ---------------------------------------------------------------------------------------------------------------------
async def setup(bot):
    os.makedirs('data/welcome', exist_ok=True)
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS event_config (
            guild_id INTEGER PRIMARY KEY,
            default_role_id INTEGER,
            default_channel_id INTEGER,
            welcome_message TEXT DEFAULT 'Welcome to the server, {member}!',
            background_colour TEXT DEFAULT '#EDDCFE', 
            background_image TEXT DEFAULT NULL,
            avatar_ring_colour TEXT DEFAULT '#C891F9',
            text_overlay TEXT DEFAULT "'{member}' has just joined the server",
            text_color TEXT DEFAULT '#000000' 
        )
        ''')
        await conn.commit()
    await bot.add_cog(EventCog(bot))