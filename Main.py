import discord
from discord.ext import tasks, commands
import openai
import os
import random
import asyncio
from datetime import datetime
import aiohttp

# No cargar .env en producción (Render lo maneja con variables de entorno)
# Las variables se leen directamente de os.getenv()

class AIBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        intents.reactions = True
        intents.guilds = True
        
        super().__init__(intents=intents)
        
        # Cargar prompt desde archivo
        try:
            with open('prompt.txt', 'r', encoding='utf-8') as file:
                self.base_prompt = file.read()
            print("✅ Prompt cargado correctamente")
        except Exception as e:
            print(f"❌ Error cargando prompt: {e}")
            self.base_prompt = "Eres un asistente útil."
        
        # Obtener variables de entorno de Render
        self.discord_token = os.getenv('DISCORD_TOKEN')
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        
        # Configurar canales (opcional)
        channel_ids = os.getenv('CHANNEL_IDS', '')
        self.channel_ids = [int(x.strip()) for x in channel_ids.split(',') if x.strip()] if channel_ids else []
        
        # Configurar OpenAI
        if self.openai_api_key:
            openai.api_key = self.openai_api_key
        else:
            print("⚠️  OPENAI_API_KEY no configurada")
        
        self.conversation_histories = {}
        self.last_random_message = {}

    async def setup_hook(self):
        # Verificar que tenemos el token de Discord
        if not self.discord_token:
            print("❌ DISCORD_TOKEN no configurado")
            return
            
        self.random_message_task.start()
        print("🤖 Bot iniciado y tareas programadas")

    async def on_ready(self):
        print(f'✅ {self.user} se ha conectado a Discord!')
        print(f'📊 Conectado a {len(self.guilds)} servidores')
        print(f'🎯 Canales designados: {self.channel_ids if self.channel_ids else "Todos los canales"}')

    # ... (el resto del código permanece igual)

# Verificar variables críticas antes de iniciar
if __name__ == "__main__":
    required_vars = ['DISCORD TOKEN', 'OPENAI_API_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Variables faltantes: {', '.join(missing_vars)}")
        print("💡 Configúralas en Render.com → Environment Variables")
        exit(1)
    
    bot = AIBot()
    bot.run(os.getenv('DISCORD_TOKEN'))            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"❌ Error con OpenAI: {e}")
            return None

    def get_recent_conversation_preview(self, channel_id):
        """Obtener vista previa de la conversación reciente"""
        history = self.conversation_histories.get(channel_id, [])
        recent = history[-5:]  # Últimos 5 mensajes
        return " | ".join([f"{msg['role']}: {msg['content'][:50]}..." for msg in recent])

    async def on_message(self, message):
        # Ignorar mensajes del bot
        if message.author == self.user:
            return
        
        # Solo actuar en canales designados (si hay específicos)
        if CHANNEL_IDS and message.channel.id not in CHANNEL_IDS:
            return
        
        channel_id = message.channel.id
        
        # Inicializar historial del canal si no existe
        if channel_id not in self.conversation_histories:
            self.conversation_histories[channel_id] = []
        
        # Guardar mensaje en historial
        self.conversation_histories[channel_id].append({
            "role": "user",
            "content": message.content,
            "timestamp": datetime.now()
        })
        
        # Limitar historial a 50 mensajes por canal
        if len(self.conversation_histories[channel_id]) > 50:
            self.conversation_histories[channel_id] = self.conversation_histories[channel_id][-50:]
        
        # Responder si mencionan al bot o responden a un mensaje del bot
        should_respond = (
            self.user in message.mentions or
            (message.reference and message.reference.resolved and 
             message.reference.resolved.author == self.user)
        )
        
        if should_respond:
            async with message.channel.typing():
                response = await self.get_ai_response(message.content, channel_id)
                
                if response:
                    # Dividir respuesta si es muy larga
                    if len(response) > 2000:
                        chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
                        for chunk in chunks:
                            await message.reply(chunk)
                    else:
                        await message.reply(response)
                    
                    # Guardar respuesta del bot en historial
                    self.conversation_histories[channel_id].append({
                        "role": "assistant",
                        "content": response,
                        "timestamp": datetime.now()
                    })

    @tasks.loop(minutes=2)  # Revisar cada 2 minutos
    async def random_message_task(self):
        """Tarea para enviar mensajes aleatorios ocasionales"""
        try:
            # 15% de probabilidad de enviar mensaje aleatorio en cada ejecución
            if random.random() < 0.15:
                channels_to_check = []
                
                # Obtener canales designados o todos los canales accesibles
                for guild in self.guilds:
                    for channel in guild.text_channels:
                        if CHANNEL_IDS and channel.id not in CHANNEL_IDS:
                            continue
                        
                        # Verificar permisos
                        if channel.permissions_for(guild.me).send_messages:
                            channels_to_check.append(channel)
                
                if not channels_to_check:
                    return
                
                # Elegir canal aleatorio
                channel = random.choice(channels_to_check)
                channel_id = channel.id
                
                # Verificar que haya pasado al menos 10 minutos desde el último mensaje aleatorio
                last_message = self.last_random_message.get(channel_id)
                if last_message and (datetime.now() - last_message).total_seconds() < 600:
                    return
                
                # Verificar actividad reciente en el canal
                try:
                    recent_messages = []
                    async for msg in channel.history(limit=10):
                        if msg.author != self.user and not msg.content.startswith('!'):
                            recent_messages.append(msg.content)
                    
                    if not recent_messages:
                        return
                        
                except Exception as e:
                    print(f"❌ Error revisando historial del canal {channel_id}: {e}")
                    return
                
                # Generar mensaje aleatorio
                async with channel.typing():
                    response = await self.get_ai_response("", channel_id, is_random=True)
                    
                    if response:
                        await channel.send(response)
                        self.last_random_message[channel_id] = datetime.now()
                        
                        # Guardar en historial
                        if channel_id in self.conversation_histories:
                            self.conversation_histories[channel_id].append({
                                "role": "assistant",
                                "content": response,
                                "timestamp": datetime.now()
                            })
                        
                        print(f"📨 Mensaje aleatorio enviado en #{channel.name}")
                        
        except Exception as e:
            print(f"❌ Error en tarea de mensajes aleatorios: {e}")

    @random_message_task.before_loop
    async def before_random_message_task(self):
        """Esperar a que el bot esté listo"""
        await self.wait_until_ready()

# Ejecutar el bot
if __name__ == "__main__":
    bot = AIBot()
    bot.run(DISCORD_TOKEN)
