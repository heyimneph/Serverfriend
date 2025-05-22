import discord
import logging
import aiosqlite
import time
from discord.ext import commands
from discord.ui import Button, View

# ----------------------------------------------------------------------------------------------------------------------
# Database Configuration
# ----------------------------------------------------------------------------------------------------------------------
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


# ----------------------------------------------------------------------------------------------------------------------
# AntiSpamCog Class
# ----------------------------------------------------------------------------------------------------------------------

class AntiSpamCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_message_log = {}
        self.spam_threshold = 5
        self.time_frame = 3
        self.restricted_users = {}

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        now = time.time()
        user_id = message.author.id

        if user_id not in self.user_message_log:
            self.user_message_log[user_id] = []

        self.user_message_log[user_id] = [msg_time for msg_time in self.user_message_log[user_id] if now - msg_time < self.time_frame]
        self.user_message_log[user_id].append(now)

        if len(self.user_message_log[user_id]) > self.spam_threshold:
            await self.handle_spam(message)

    async def handle_spam(self, message):
        user = message.author
        guild = message.guild
        if user.id in self.restricted_users:
            return  # Skip if the user is already restricted

        logger.warning(f"User {user.name} ({user.id}) detected as spamming in guild {guild.name} ({guild.id}).")
        await self.restrict_user_permissions(guild, user)
        await self.log_restriction(guild, user, "Spamming")

    async def restrict_user_permissions(self, guild, user):
        restricted_role = discord.utils.get(guild.roles, name="Restricted")
        if not restricted_role:
            restricted_role = await guild.create_role(name="Restricted", permissions=discord.Permissions.none())

        role_ids = [role.id for role in user.roles if role != guild.default_role]

        async with aiosqlite.connect(db_path) as db:
            await db.execute('''
                INSERT INTO restricted_users (user_id, guild_id, role_ids) 
                VALUES (?, ?, ?) 
                ON CONFLICT(user_id, guild_id) DO UPDATE SET role_ids = excluded.role_ids
            ''', (user.id, guild.id, ','.join(map(str, role_ids))))
            await db.commit()

        await user.remove_roles(*[role for role in user.roles if role != guild.default_role], reason="Spamming")
        await user.add_roles(restricted_role, reason="Spamming")
        self.restricted_users[user.id] = time.time()  # Log the restriction time

    async def restore_user_roles(self, guild, user):
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute('''
                SELECT role_ids FROM restricted_users WHERE user_id = ? AND guild_id = ?
            ''', (user.id, guild.id))
            result = await cursor.fetchone()

        if result:
            role_ids = [int(role_id) for role_id in result[0].split(',') if role_id.isdigit()]
            roles = [discord.utils.get(guild.roles, id=role_id) for role_id in role_ids]
            restricted_role = discord.utils.get(guild.roles, name="Restricted")

            await user.remove_roles(restricted_role, reason="Restoring roles")
            await user.add_roles(*roles, reason="Restoring roles")

            async with aiosqlite.connect(db_path) as db:
                await db.execute('DELETE FROM restricted_users WHERE user_id = ? AND guild_id = ?', (user.id, guild.id))
                await db.commit()

            if user.id in self.restricted_users:
                del self.restricted_users[user.id]  # Clear the log for this user

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


# ----------------------------------------------------------------------------------------------------------------------
# Setup Function
# ----------------------------------------------------------------------------------------------------------------------

async def setup(bot):
    async with aiosqlite.connect(db_path) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS restricted_users (
                user_id INTEGER,
                guild_id INTEGER,
                role_ids TEXT,
                PRIMARY KEY (user_id, guild_id)
            )
        ''')
        await db.commit()

    await bot.add_cog(AntiSpamCog(bot))
