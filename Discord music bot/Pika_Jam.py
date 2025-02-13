from ast import alias
import discord
from discord.ext import commands
from youtubesearchpython import VideosSearch
from yt_dlp import YoutubeDL
import asyncio

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.is_playing = False
        self.is_paused = False
        self.music_queue = []
        self.YDL_OPTIONS = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True, 'retries': 5, 'fragment_retries': 5}
        self.recently_played = []
        self.FFMPEG_OPTIONS = {'options': '-vn'}
        self.vc = None
        self.ytdl = YoutubeDL(self.YDL_OPTIONS)

    def search_yt(self, query):
        if query.startswith('http://') or query.startswith('https://'):
            title = self.ytdl.extract_info(query, download=False)['title']
            return {'source': query, 'title': title}
        else:
            videos_search = VideosSearch(query, limit=1)
            results = videos_search.result()
            if results and 'result' in results and len(results['result']) > 0:
                return {'source': results['result'][0]['link'], 'title': results['result'][0]['title']}
            else:
                return None

    async def play_next(self, ctx):
        if len(self.music_queue) > 0:
            self.is_playing = True
            song = self.music_queue.pop(0)
            m_url = song['source']

            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: self.ytdl.extract_info(m_url, download=False))
            audio_url = data['url']
            source = await discord.FFmpegOpusAudio.from_probe(audio_url, options=f'-vn -filter:a "volume={self.volume_level}"')
            self.vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop))
            await ctx.send(f"Now playing: {song['title']}")
            self.recently_played.append(song)
            if len(self.recently_played) > 10:
                self.recently_played.pop(0)
        else:
            self.is_playing = False

    async def play_music(self, ctx):
        if len(self.music_queue) > 0:
            self.is_playing = True
            song = self.music_queue[0]
            m_url = song['source']

            if self.vc == None or not self.vc.is_connected():
                self.vc = await song['channel'].connect()
                await self.vc.guild.change_voice_state(channel=self.vc.channel, self_deaf=True)
                if self.vc == None:
                    await ctx.send("Could not connect to the voice channel.")
                    return
            else:
                await self.vc.move_to(song['channel'])

            self.music_queue.pop(0)
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: self.ytdl.extract_info(m_url, download=False))
            audio_url = data['url']
            source = await discord.FFmpegOpusAudio.from_probe(audio_url, **self.FFMPEG_OPTIONS)
            self.vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop))
            await ctx.send(f"Now playing: {song['title']}")
        else:
            self.is_playing = False

    @commands.command(name='play', aliases=['p', 'playing'], help='Plays a selected song from YouTube')
    async def play(self, ctx, *args):
        query = " ".join(args)
        voice_channel = ctx.author.voice.channel if ctx.author.voice else None

        if voice_channel is None:
            await ctx.send("You need to be in a voice channel first!")
            return

        if self.is_paused:
            self.vc.resume()
        else:
            song = self.search_yt(query)
            if song is None:
                await ctx.send("Could not find any results for your query.")
            else:
                song['channel'] = voice_channel
                self.music_queue.append(song)
                if not self.is_playing:
                    await self.play_music(ctx)
                else:
                    await ctx.send(f"Added to queue: {song['title']}")

    @commands.command(name='volume', aliases=['vol'], help='Sets the volume of the player (0-100)')
    async def volume(self, ctx, volume: int):
        if self.vc is None or not self.vc.is_connected():
            await ctx.send("Bot is not connected to a voice channel.")
            return
        if 0 <= volume <= 100:
            self.volume_level = volume / 100.0
            await ctx.send(f"Volume set to {volume}%")
        else:
            await ctx.send("Volume must be between 0 and 100.")

    @commands.command(name='pause', help='Pauses the current song being played')
    async def pause(self, ctx):
        if self.is_playing:
            self.is_playing = False
            self.is_paused = True
            self.vc.pause()
            await ctx.send("Playback paused.")

    @commands.command(name='resume', aliases=['r'], help='Resumes playing with the discord bot')
    async def resume(self, ctx):
        if self.is_paused:
            self.is_paused = False
            self.is_playing = True
            self.vc.resume()
            await ctx.send("Playback resumed.")

    @commands.command(name='skip', aliases=['s'], help='Skips the current song being played')
    async def skip(self, ctx):
        if self.vc != None and self.is_playing:
            self.vc.stop()
            await self.play_music(ctx)

    @commands.command(name='queue', aliases=['q'], help='Displays the current songs in queue')
    async def queue(self, ctx):
        if len(self.music_queue) == 0:
            await ctx.send("The queue is currently empty.")
        else:
            queue_list = "\n".join([f"#{idx + 1} - {song['title']}" for idx, song in enumerate(self.music_queue)])
            await ctx.send(f"Current queue:\n{queue_list}")

    @commands.command(name='recent', help='Displays recently played songs and allows adding them back to the queue')
    async def recent(self, ctx):
        if len(self.recently_played) == 0:
            await ctx.send("No recently played songs.")
        else:
            recent_list = "\n".join([f"#{idx + 1} - {song['title']}" for idx, song in enumerate(self.recently_played)])
            await ctx.send(f"Recently played songs:\n{recent_list}\nType '//add <number>' to add a song back to the queue.")

    @commands.command(name='add', help='Adds a recently played song back to the queue')
    async def add(self, ctx, index: int):
        if 1 <= index <= len(self.recently_played):
            song = self.recently_played[index - 1]
            voice_channel = ctx.author.voice.channel if ctx.author.voice else None

            if voice_channel is None:
                await ctx.send("You need to be in a voice channel first!")
                return

            song['channel'] = voice_channel
            self.music_queue.append(song)
            await ctx.send(f"Added to queue: {song['title']}")
            if not self.is_playing:
                await self.play_music(ctx)
        else:
            await ctx.send("Invalid song number.")

    @commands.command(name='clear', aliases=['c', 'bin'], help='Stops the music and clears the queue')
    async def clear(self, ctx):
        if self.vc != None and self.is_playing:
            self.vc.stop()
        self.music_queue = []
        await ctx.send("Music queue cleared.")

    @commands.command(name='stop', aliases=['disconnect', 'l', 'd','leave'], help='Disconnects the bot from VC')
    async def dc(self, ctx):
        self.is_playing = False
        self.is_paused = False
        await self.vc.disconnect()
        await ctx.send("Disconnected from the voice channel.")

    @commands.command(name='remove', help='Removes the last song added to queue')
    async def remove(self, ctx):
        if len(self.music_queue) > 0:
            removed_song = self.music_queue.pop()
            await ctx.send(f"Removed from queue: {removed_song['title']}")
        else:
            await ctx.send("The queue is already empty.")

# Bot setup
def token():
    try:
        with open('Token.txt', 'r') as f:
            token = f.readline().strip()
        return token
    except FileNotFoundError:
        print("Token file not found.")
        return None

TOKEN = token()

intents = discord.Intents.default()
intents.message_content = True  # Make sure your bot has this intent enabled
bot = commands.Bot(command_prefix='//', intents=intents)

# Add the music cog to the bot
@bot.event
async def on_ready():
    await bot.add_cog(MusicCog(bot))
    print(f'Logged in as {bot.user}')

bot.run(TOKEN)
