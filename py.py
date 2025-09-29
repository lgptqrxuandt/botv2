# bot.py
import os
import re
import json
import asyncio
from collections import defaultdict
from typing import Optional

import discord
from discord.ext import commands
import openai

# ---------- CONFIG ----------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PREFIX = "!"
WARNINGS_FILE = "warnings.json"
# ----------------------------

if not DISCORD_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("Set DISCORD_TOKEN and OPENAI_API_KEY environment variables.")

openai.api_key = OPENAI_API_KEY

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)
warnings = defaultdict(int)

# Try load persisted warnings
if os.path.exists(WARNINGS_FILE):
    try:
        with open(WARNINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            warnings.update({int(k): int(v) for k, v in data.items()})
    except Exception:
        warnings = defaultdict(int)

# ---------- Helpers ----------
def contains_arabic(text: str) -> bool:
    # quick check for Arabic letters
    return any("\u0600" <= ch <= "\u06FF" or "\u0750" <= ch <= "\u077F" for ch in text)

def short_cleanup(text: str) -> str:
    return text.strip()

async def ask_openai(prompt: str, user_lang: str = "en") -> str:
    """
    Ask OpenAI ChatCompletion for response. We run the call in a thread to avoid blocking.
    """
    system_msg = "You are a chill friendly Discord assistant. Keep replies brief, helpful, and friendly."
    # If Arabic, hint that reply should be Arabic.
    if user_lang == "ar":
        system_msg = "You are a chill friendly Arabic-speaking Discord assistant. Reply in Arabic, friendly and concise."
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt}
    ]
    def blocking_call():
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=600,
            temperature=0.6
        )
        return resp
    resp = await asyncio.to_thread(blocking_call)
    return resp["choices"][0]["message"]["content"].strip()

def persist_warnings():
    try:
        with open(WARNINGS_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in warnings.items()}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ---------- Moderation ----------
BANNED_WORDS = {"noxiousword1", "noxiousword2"}  # replace with actual words you want blocked
SPAM_THRESHOLD = 5  # messages in short time (basic)

recent_messages = defaultdict(list)  # member_id -> [timestamps]

async def handle_moderation(message: discord.Message):
    author = message.author
    if author.bot:
        return

    content = message.content.lower()

    # 1) banned words
    for bad in BANNED_WORDS:
        if bad in content:
            try:
                await message.delete()
            except Exception:
                pass
            warnings[author.id] += 1
            persist_warnings()
            await message.channel.send(f"<@{author.id}> Please do not use that language. Warning {warnings[author.id]}.")
            return

    # 2) spam simple heuristic: repeated same message
    recent = recent_messages[author.id]
    recent.append(message.created_at.timestamp())
    # keep only last 10 seconds window
    cutoff = message.created_at.timestamp() - 10
    recent_messages[author.id] = [t for t in recent if t >= cutoff]

    # quick repeated content spam check
    history = [m.content for m in await message.channel.history(limit=10).flatten()]
    if history.count(message.content) > 3:
        try:
            await message.delete()
        except Exception:
            pass
        warnings[author.id] += 1
        persist_warnings()
        await message.channel.send(f"<@{author.id}> Slow down with repeated messages. Warning {warnings[author.id]}.")
        return

    # 3) soft actions based on warning count
    if warnings[author.id] >= 3:
        # mute for a short time if possible (needs Manage Roles & a 'Muted' role)
        await message.channel.send(f"<@{author.id}> You have multiple warnings. Please calm down — staff will review this.")
        # don't auto-ban in chill mode

# ---------- Bot behavior ----------
@bot.event
async def on_ready():
    print(f"Bot ready: {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Run moderation in background but awaited so decisions happen
    await handle_moderation(message)

    # Decide when to reply:
    # - If the bot is mentioned
    # - If message starts with prefix + 'ai' or 'ask' or 'fix'
    # - If DM to bot
    content = message.content.strip()
    is_mention = bot.user in message.mentions
    trigger_prefix = False
    triggers = (f"{PREFIX}ai", f"{PREFIX}ask", f"{PREFIX}fix", f"{PREFIX}scripthelp")
    if any(content.lower().startswith(t) for t in triggers):
        trigger_prefix = True

    if isinstance(message.channel, discord.DMChannel) or is_mention or trigger_prefix:
        # build prompt to send to OpenAI
        # If the user included a code block, pass it through clearly
        code_blocks = re.findall(r"```(?:[\s\S]*?)```", content)
        user_lang = "ar" if contains_arabic(content) else "en"
        # If they used a command like !fix, try to detect code in following message or code block
        prompt = content
        if code_blocks:
            prompt = "Please help fix or explain the following code:\n\n" + "\n\n".join(code_blocks)
        elif trigger_prefix:
            # remove the command token to leave the message body
            for t in triggers:
                if content.lower().startswith(t):
                    prompt = content[len(t):].strip()
                    break
            if not prompt:
                prompt = "Say hi and offer help. Ask what they need."

        # Personalize system style: chill voice
        if user_lang == "ar":
            prompt = "(Reply in Egyptian Arabic, chill/friendly tone)\n\n" + prompt
        else:
            prompt = "(Reply in chill friendly English, like a real friend)\n\n" + prompt

        try:
            reply = await ask_openai(prompt, user_lang=user_lang)
        except Exception as e:
            reply = "Sorry, I couldn't reach the AI right now. Try again later."
            print("OpenAI error:", e)

        # Send as a normal reply (not embed) to feel chatty
        try:
            await message.reply(reply, mention_author=False)
        except Exception:
            await message.channel.send(reply)

    # process commands as well
    await bot.process_commands(message)

# ---------- Commands ----------
@bot.command(name="warns")
@commands.has_permissions(manage_messages=True)
async def warns(ctx: commands.Context, member: Optional[discord.Member] = None):
    member = member or ctx.author
    count = warnings.get(member.id, 0)
    await ctx.send(f"{member.mention} has {count} warning(s).")

@bot.command(name="fix")
async def fix_cmd(ctx: commands.Context, *, body: Optional[str] = None):
    """
    Usage:
    !fix <paste your code or question>
    Or reply to a message with code and type: !fix
    """
    content = body or ""
    # if command is used as a reply, use replied message
    if ctx.message.reference and not content:
        ref = ctx.message.reference
        try:
            replied = await ctx.channel.fetch_message(ref.message_id)
            content = replied.content
        except Exception:
            pass

    # try to extract code block if present
    code_blocks = re.findall(r"```(?:[a-zA-Z]*)\n([\s\S]*?)```", content)
    user_lang = "ar" if contains_arabic(content) else "en"
    if code_blocks:
        prompt = "Fix this code and explain the changes briefly:\n\n" + code_blocks[0]
    elif content:
        prompt = "Help with: " + content
    else:
        await ctx.send("Send the code or message after the command, or reply to a message with code and use `!fix`.")
        return

    if user_lang == "ar":
        prompt = "(Reply in Egyptian Arabic, chill helper tone)\n\n" + prompt
    else:
        prompt = "(Reply in chill helpful English)\n\n" + prompt

    await ctx.send("Working on it... (this can take a few seconds)")
    try:
        reply = await ask_openai(prompt, user_lang=user_lang)
    except Exception as e:
        reply = "Sorry, failed to contact the assistant. Try again later."
        print("OpenAI error:", e)

    # send reply but keep message length reasonable
    # split long replies into code blocks or parts
    if len(reply) > 1900:
        # try to split by new lines
        parts = [reply[i:i+1900] for i in range(0, len(reply), 1900)]
        for p in parts:
            await ctx.send(p)
    else:
        await ctx.send(reply)

@bot.command(name="rules")
async def rules_cmd(ctx: commands.Context):
    text = (
        "**📜 Server Rules**\n"
        "1. Be respectful. No harassment, racism, or hate.\n"
        "2. No spam or unnecessary mentions.\n"
        "3. Use channels correctly.\n"
        "4. No NSFW or illegal content.\n"
        "5. Listen to staff.\n"
        "If you break rules you'll get warnings. Stay chill.\n"
    )
    await ctx.send(text)

# ---------- Run ----------
try:
    bot.run(DISCORD_TOKEN)
finally:
    persist_warnings()
