#!/usr/bin/env python3

import asyncio
import datetime
import discord # Requires rewrite branch
from discord.ext import commands
import json
import logging
import pickle

from apply_handling import new_app
from channel_handling import get_channel
from dwarves import show_dwarves
from initialise import initialise
from raid_handling import raid_command, raid_update, Tier, Time
from raid import Raid
from reaction_handling import role_update
from role_handling import show_roles

logging.basicConfig(level=logging.INFO)

# If testing it will skip 10s delay.
launch_on_boot = False

# print version number.
version = "v2.1.4"
print("Running " + version)

# Load config file.
with open('config.json','r') as f:
    config = json.load(f)

# Assign specified config values.
token = config['DEFAULT']['BOT_TOKEN']
serverid = config['DISCORD']['SERVER_ID']

# Specify names for channels the bot will respond in.
# These will be automatically created on the server if they do not exist.
channel_names = {
    'BOT': 'saruman',
    'APPLY': 'applications'
}

# Specify names for class roles.
# These will be automatically created on the server if they do not exist.
role_names = ("Beorning","Burglar","Captain","Champion","Guardian","Hunter","Loremaster","Minstrel","Runekeeper","Warden")
boss_name = "witch_king"
raid_leader_name = "Raid Leader"

raids = []
# Load the saved raid posts from file.
try:
    with open('raids.pkl','rb') as f:
        raids = pickle.load(f)
except (OSError,IOError) as e:
    pass
print("We have the following raid data in memory.")
for raid in raids:
    print(raid)

def save(raids):
    with open('raids.pkl', 'wb') as f:
        pickle.dump(raids, f)
    print("Saved raids to file at:")
    print(datetime.datetime.now())

if launch_on_boot:
    # On boot the system launches the bot fater than it gains internet access.
    # Avoid all the resulting errors.
    print("Waiting 10s for system to gain internet access.")
    asyncio.sleep(10)
print("Continuing...")

prefix = "!"
bot = commands.Bot(command_prefix=prefix,case_insensitive=True)

async def background_task():
    await bot.wait_until_ready()
    while not bot.is_closed():
        await asyncio.sleep(3600)
        current_time = datetime.datetime.now()
        delta_time = datetime.timedelta(seconds=7200)
        # Copy the list to iterate over.
        for raid in raids[:]:
            if raid.time + delta_time < current_time:
                # Look for the channel in which the raid post is.
                for guild in bot.guilds:
                    for channel in guild.text_channels:
                        try:
                            post = await channel.fetch_message(raid.post_id)
                        except (discord.NotFound, discord.Forbidden):
                            continue
                        else:
                            await post.delete()
                            print("Deleted old raid post.")
                            break
                raids.remove(raid)
                print("Deleted old raid.")
        # Save raids to file
        save(raids)

@bot.event
async def on_ready():
    print("We have logged in as {0.user}".format(bot))
    print("The time is:")
    print(datetime.datetime.now())
    await bot.change_presence(activity=discord.Game(name=version))
    for guild in bot.guilds:
        print('Welcome to {0}'.format(guild))

    global role_post_ids
    role_post_ids = []
    for guild in bot.guilds:
        # Initialise the role post in the bot channel.
        try:
            bot_channel = await get_channel(guild,channel_names['BOT'])
            role_post = await initialise(guild,bot_channel,role_names)
        except discord.Forbidden:
            print("Missing permissions for {0}".format(guild.name))
        else:
            role_post_ids.append(role_post.id)
    
@bot.event
async def on_reaction_add(reaction,user):
    # Check if the reaction is by the bot itself.
    if user == bot.user:
        return 
    # Check if the reaction is to the role post.
    if reaction.message.id in role_post_ids:
        await role_update(reaction,user,role_names)

@bot.event
async def on_raw_reaction_add(payload):
    guild = bot.get_guild(payload.guild_id)
    update = False
    for raid in raids:
        if payload.message_id == raid.post_id:
            update = await raid_update(bot,payload,guild,raid,role_names,boss_name,raid_leader_name)
            break
    # if update:
        # save(raids)

@bot.event
async def on_reaction_remove(reaction,user):
    pass

@bot.event
async def on_command_error(ctx,error):
    print("Command given: " + ctx.message.content)
    print(error)
    if isinstance(error, commands.NoPrivateMessage):
        await ctx.send("Please use this command in a server.")
    else:
        await ctx.send(error,delete_after=10)

@bot.check
async def globally_block_dms(ctx):
    if ctx.guild is None:
        raise commands.NoPrivateMessage("No dm allowed!")
    else:
        return True

@bot.command()
async def roles(ctx):
    """Shows the class roles you have"""
    await show_roles(ctx.channel,ctx.author,role_names)

@bot.command()
async def dwarves(ctx):
    """Shows abilities of dwarves in Anvil"""
    await show_dwarves(ctx.channel)

@bot.command()
async def apply(ctx):
    """Apply to the kin"""
    await new_app(bot,ctx.message,channel_names['APPLY'])

@bot.command()
async def raid(ctx,name,tier: Tier,boss,*,time: Time):
    """Schedules a raid"""
    raid = await raid_command(ctx,name,tier,boss,time,role_names,boss_name)
    raids.append(raid)
    save(raids)

raid_brief = "Schedules a raid"
raid_description = "Schedules a raid. Day/timezone will default to today/UTC if not specified. You can use 'server' as timezone. Usage:"
raid_example = "Examples:\n!raid Anvil 2 all Friday 4pm server\n!raid throne t3 2-4 21:00"
raid.update(help=raid_example,brief=raid_brief,description=raid_description)

@bot.command()
async def anvil(ctx,*,time: Time):
    """Shortcut to schedule Anvil raid"""
    try:
        tier = await Tier().converter(ctx.channel.name)
    except commands.BadArgument:
        await ctx.send("Channel name does not specify tier.")
    else:
        raid = await raid_command(ctx,"Anvil",tier,"All",time,role_names,boss_name)
        raids.append(raid)
        save(raids)

anvil_brief = "Shortcut to schedule an Anvil raid"
anvil_description = "Schedules a raid with name 'Anvil', tier from channel name and bosses 'All'. Day/timezone will default to today/UTC if not specified. You can use 'server' as timezone. Usage:"
anvil_example = "Examples:\n!anvil Friday 4pm server\n!anvil 21:00 BST"
anvil.update(help=anvil_example,brief=anvil_brief,description=anvil_description)

@bot.command()
@commands.is_owner()
async def delete(ctx,msg_id: int):
    """Deletes a message"""
    msg = await ctx.channel.fetch_message(msg_id)
    await ctx.message.delete()
    await asyncio.sleep(0.25)
    await msg.delete()

delete.update(hidden=True)

@delete.error
async def delete_error(ctx,error):
    if isinstance(error, commands.NotOwner):
        ctx.send("You do not have permission to use this command.")

bot.loop.create_task(background_task())
bot.run(token)

# Save raids if bot unexpectedly closes.
save(raids)
print("Shutting down.")
