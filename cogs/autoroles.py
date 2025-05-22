import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import os

# ---------------------------------------------------------------------------------------------------------------------
# Database Configuration
# ---------------------------------------------------------------------------------------------------------------------

os.makedirs('./data/databases', exist_ok=True)
db_path = './data/databases/serverfriend.db'

# ---------------------------------------------------------------------------------------------------------------------
# Autorole Cog
# ---------------------------------------------------------------------------------------------------------------------

class AutoRoleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------------------------------------------------------------------------------------------------------------------
    # Autorole Commands
    # ---------------------------------------------------------------------------------------------------------------------

    @app_commands.command(name="setup_autorole", description="Admin: Set up the autorole message.")
    @app_commands.describe(channel="The channel where the autorole message will be sent")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_autorole(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)

        # Hardcoded message for autorole selection
        message = (
            "Welcome to our server! Once you've read the rules, choose the 'Member' role to see other channels. "
            "Please select any other roles by reacting to this message: \n\n"
            "✅ - Member \n"
            "<:nephbox:1271580297024245771> - Nephbox\n"
            "<:misu:1271580394583625728> - Misu\n"
            "🖥️ - Gamer \n\n"
            
            "You can remove a role by removing your reaction. \n\n"
            
            "**roles determine which future annoucements you will recieve*"
        )

        # Send the autorole message
        msg = await channel.send(message)

        # Add reactions for roles
        role_emojis = ['✅', '<:nephbox:1271580297024245771>', '<:misu:1271580394583625728>', '🖥️']
        for emoji in role_emojis:
            await msg.add_reaction(emoji)

        async with aiosqlite.connect(db_path) as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS autorole_message (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL
                )
            ''')
            await conn.execute('''
                INSERT OR REPLACE INTO autorole_message (guild_id, channel_id, message_id)
                VALUES (?, ?, ?)
            ''', (interaction.guild.id, channel.id, msg.id))
            await conn.commit()

        await interaction.followup.send(f"Autorole message set up in {channel.mention}.", ephemeral=True)

    # ---------------------------------------------------------------------------------------------------------------------
    # Event Listeners
    # ---------------------------------------------------------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute('SELECT channel_id, message_id FROM autorole_message WHERE guild_id = ?',
                                        (guild.id,))
            result = await cursor.fetchone()

        if result:
            channel_id, message_id = result
            if payload.message_id == message_id and payload.channel_id == channel_id:
                member = guild.get_member(payload.user_id)
                if not member:
                    return

                # Define your role emojis here
                role_mapping = {
                    '✅': 'Member',
                    '<:nephbox:1271580297024245771>': 'Nephbox',
                    '<:misu:1271580394583625728>': 'Misu',
                    '🖥️': 'Gamer'
                }

                role_name = role_mapping.get(str(payload.emoji))
                if role_name:
                    role = discord.utils.get(guild.roles, name=role_name)
                    if role:
                        await member.add_roles(role)

    # Function to remove roles when reaction is removed
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute('SELECT channel_id, message_id FROM autorole_message WHERE guild_id = ?',
                                        (guild.id,))
            result = await cursor.fetchone()

        if result:
            channel_id, message_id = result
            if payload.message_id == message_id and payload.channel_id == channel_id:
                member = guild.get_member(payload.user_id)
                if not member:
                    return

                # Define your role emojis here
                role_mapping = {
                    '✅': 'Member',
                    '<:nephbox:1271580297024245771>': 'Nephbox',
                    '<:misu:1271580394583625728>': 'Misu',
                    '🖥️': 'Gamer'
                }

                role_name = role_mapping.get(str(payload.emoji))
                if role_name:
                    role = discord.utils.get(guild.roles, name=role_name)
                    if role:
                        await member.remove_roles(role)

# ---------------------------------------------------------------------------------------------------------------------
# Setup Function
# ---------------------------------------------------------------------------------------------------------------------

async def setup(bot):
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS autorole_message (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL
            )
        ''')
        await conn.commit()
    await bot.add_cog(AutoRoleCog(bot))
