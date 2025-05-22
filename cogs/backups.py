import os
import json
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime

# ---------------------------------------------------------------------------------------------------------------------
# Backup and Restore Cog Class
# ---------------------------------------------------------------------------------------------------------------------

class BackupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backup_dir = './data/backups'
        os.makedirs(self.backup_dir, exist_ok=True)
        self.daily_backup_task.start()

    def cog_unload(self):
        self.daily_backup_task.cancel()

    async def backup_guild(self, guild):
        backup_data = {
            'id': guild.id,
            'name': guild.name,
            'roles': [],
            'channels': [],
            'categories': [],
            'members': []
        }

        # Backup Roles
        for role in guild.roles:
            backup_data['roles'].append({
                'id': role.id,
                'name': role.name,
                'permissions': role.permissions.value,
                'color': role.color.value,  #
                'hoist': role.hoist,
                'position': role.position,
                'mentionable': role.mentionable
            })

        # Backup Categories
        for category in guild.categories:
            backup_data['categories'].append({
                'id': category.id,
                'name': category.name,
                'position': category.position,
                'permissions_overwrites': [
                    {
                        'id': target.id,
                        'type': 'role' if isinstance(target, discord.Role) else 'member',
                        'allow': overwrite.pair()[0].value,
                        'deny': overwrite.pair()[1].value
                    }
                    for target, overwrite in category.overwrites.items()
                ]
            })

        # Backup Channels
        for channel in guild.channels:
            if isinstance(channel, discord.TextChannel) or isinstance(channel, discord.VoiceChannel):
                backup_data['channels'].append({
                    'id': channel.id,
                    'name': channel.name,
                    'type': 'text' if isinstance(channel, discord.TextChannel) else 'voice',
                    'position': channel.position,
                    'topic': getattr(channel, 'topic', None),
                    'nsfw': getattr(channel, 'nsfw', False),
                    'category': channel.category.id if channel.category else None,
                    'permissions_overwrites': [
                        {
                            'id': target.id,
                            'type': 'role' if isinstance(target, discord.Role) else 'member',
                            'allow': overwrite.pair()[0].value,
                            'deny': overwrite.pair()[1].value
                        }
                        for target, overwrite in channel.overwrites.items()
                    ]
                })

        # Backup Members
        for member in guild.members:
            backup_data['members'].append({
                'id': member.id,
                'name': member.name,
                'roles': [role.id for role in member.roles]
            })

        # Create a filename with date and time
        timestamp = datetime.utcnow().strftime('%d-%m-%Y')
        backup_file = os.path.join(self.backup_dir, f'{timestamp}_{guild.id}.json')

        # Write backup to file
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=4)

        return backup_file

    async def restore_guild(self, guild, backup_file):
        with open(backup_file, 'r') as f:
            backup_data = json.load(f)

        # Restore Roles
        for role_data in backup_data['roles']:
            existing_role = discord.utils.get(guild.roles, id=role_data['id'])
            if existing_role is None:
                await guild.create_role(
                    name=role_data['name'],
                    permissions=discord.Permissions(role_data['permissions']),
                    color=discord.Color(role_data['color']),
                    hoist=role_data['hoist'],
                    mentionable=role_data['mentionable']
                )

        # Restore Categories
        category_mapping = {}
        for category_data in backup_data['categories']:
            existing_category = discord.utils.get(guild.categories, id=category_data['id'])
            if existing_category is None:
                new_category = await guild.create_category(
                    name=category_data['name'],
                    position=category_data['position']
                )
                category_mapping[category_data['id']] = new_category
            else:
                category_mapping[category_data['id']] = existing_category

            # Apply permissions
            overwrites = {}
            for overwrite_data in category_data['permissions_overwrites']:
                target = None
                if overwrite_data['type'] == 'role':
                    target = discord.utils.get(guild.roles, id=overwrite_data['id'])
                elif overwrite_data['type'] == 'member':
                    target = guild.get_member(overwrite_data['id'])

                if target:
                    overwrites[target] = discord.PermissionOverwrite.from_pair(
                        discord.Permissions(overwrite_data['allow']),
                        discord.Permissions(overwrite_data['deny'])
                    )

            if overwrites:
                await category_mapping[category_data['id']].edit(overwrites=overwrites)

        # Restore Channels with permission overwrites
        for channel_data in backup_data['channels']:
            category = category_mapping.get(channel_data['category'])
            existing_channel = discord.utils.get(guild.channels, id=channel_data['id'])
            if existing_channel is None:
                overwrites = {}
                for overwrite_data in channel_data['permissions_overwrites']:
                    target = None
                    if overwrite_data['type'] == 'role':
                        target = discord.utils.get(guild.roles, id=overwrite_data['id'])
                    elif overwrite_data['type'] == 'member':
                        target = guild.get_member(overwrite_data['id'])

                    if target:
                        overwrites[target] = discord.PermissionOverwrite.from_pair(
                            discord.Permissions(overwrite_data['allow']),
                            discord.Permissions(overwrite_data['deny'])
                        )

                if channel_data['type'] == 'text':
                    await guild.create_text_channel(
                        name=channel_data['name'],
                        position=channel_data['position'],
                        topic=channel_data['topic'],
                        nsfw=channel_data['nsfw'],
                        category=category,
                        overwrites=overwrites
                    )
                elif channel_data['type'] == 'voice':
                    await guild.create_voice_channel(
                        name=channel_data['name'],
                        position=channel_data['position'],
                        category=category,
                        overwrites=overwrites
                    )
            else:
                # Update permissions for existing channels
                overwrites = {}
                for overwrite_data in channel_data['permissions_overwrites']:
                    target = None
                    if overwrite_data['type'] == 'role':
                        target = discord.utils.get(guild.roles, id=overwrite_data['id'])
                    elif overwrite_data['type'] == 'member':
                        target = guild.get_member(overwrite_data['id'])

                    if target:
                        overwrites[target] = discord.PermissionOverwrite.from_pair(
                            discord.Permissions(overwrite_data['allow']),
                            discord.Permissions(overwrite_data['deny'])
                        )

                if overwrites:
                    await existing_channel.edit(overwrites=overwrites)

        # Restore Members' Roles (if they rejoin)
        for member_data in backup_data['members']:
            member = guild.get_member(member_data['id'])
            if member:
                roles = [discord.utils.get(guild.roles, id=role_id) for role_id in member_data['roles']]
                await member.edit(roles=roles)

    @app_commands.command(name="backup", description="Create a backup of the server's configuration.")
    @app_commands.checks.has_permissions(administrator=True)
    async def backup(self, interaction: discord.Interaction):
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)
        backup_file = await self.backup_guild(guild)
        await interaction.followup.send(f"Backup created: `{backup_file}`", ephemeral=True)

    @app_commands.command(name="restore", description="Restore the server's configuration from a backup.")
    @app_commands.describe(backup_name="The name of the backup file to restore")
    @app_commands.checks.has_permissions(administrator=True)
    async def restore(self, interaction: discord.Interaction, backup_name: str):
        guild = interaction.guild

        # Defer the response to avoid timeout
        await interaction.response.defer(ephemeral=True)

        backup_file = os.path.join(self.backup_dir, backup_name)

        if not os.path.exists(backup_file):
            await interaction.followup.send("Backup file not found.", ephemeral=True)
            return

        await self.restore_guild(guild, backup_file)
        await interaction.followup.send(f"Guild restored from `{backup_name}`.", ephemeral=True)

    @restore.autocomplete('backup_name')
    async def restore_autocomplete(self, interaction: discord.Interaction, current: str):
        backups = os.listdir(self.backup_dir)
        return [
            app_commands.Choice(name=backup, value=backup)
            for backup in backups if current.lower() in backup.lower()
        ]

    @tasks.loop(hours=24)
    async def daily_backup_task(self):
        for guild in self.bot.guilds:
            await self.backup_guild(guild)
            print(f"Daily backup completed for guild: {guild.name} ({guild.id})")

    @daily_backup_task.before_loop
    async def before_daily_backup(self):
        await self.bot.wait_until_ready()

# ----------------------------------------------------------------------------------------------------------------------
# Setup Function
# ----------------------------------------------------------------------------------------------------------------------

async def setup(bot):
    await bot.add_cog(BackupCog(bot))
