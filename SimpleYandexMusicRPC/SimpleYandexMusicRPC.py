import asyncio
import time
import threading
import json
import websocket
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
from yandex_music import Client
import pypresence

CLIENT_ID = "1269807014393942046"

class FastYandexRPC:
    def __init__(self):
        self.client = Client().init()
        self.rpc = None
        self.connect_rpc()
        
        
        self.track_cache = {}
        self.current_track_id = None
        self.current_track_data = None
        
        
        self.is_playing = False
        self.current_position = 0
        self.track_duration = 0
        self.last_update_time = 0
        
        
        self.ws = None
        self.ws_connected = False
        
    def connect_rpc(self):
        try:
            self.rpc = pypresence.Presence(CLIENT_ID)
            self.rpc.connect()
            print("Подключено к Дискорду")
        except Exception as e:
            print(f"Ошибка подключения к Дискорду: {e}")
            self.rpc = None
    
    def format_time(self, seconds):
        if seconds < 0:
            seconds = 0
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes}:{seconds:02d}"
    
    def find_track_fast(self, artist, title):
        """Быстрый поиск трека с кешированием"""
        cache_key = f"{artist}|{title}"
        
        
        if cache_key in self.track_cache:
            return self.track_cache[cache_key]
        
        try:
            query = f"{artist} - {title}"
            search = self.client.search(query, True, "all", 0, False)
            if search.tracks and search.tracks.results:
                track = search.tracks.results[0]
                
                self.track_cache[cache_key] = track
                return track
        except:
            pass
        return None
    
    def connect_websocket(self):
        """Подключение к WebSocket Яндекс Музыки для мгновенных обновлений"""
        def on_message(ws, message):
            try:
                data = json.loads(message)
                if data.get("command") == "player-state":
                    state = data.get("state")
                    self.is_playing = (state == "playing")
                    self.current_position = data.get("position", 0) / 1000
                    self.track_duration = data.get("duration", 0) / 1000
                elif data.get("command") == "track-info":
                    track = data.get("track")
                    if track:
                        self.current_track_data = track
                        self.current_track_id = track.get("id")
            except:
                pass
        
        def on_error(ws, error):
            self.ws_connected = False
        
        def on_close(ws, close_status_code, close_msg):
            self.ws_connected = False
        
        def on_open(ws):
            self.ws_connected = True
            print("Вебсокет подключён")
        
        
        for port in range(3400, 3411):
            try:
                ws_url = f"ws://127.0.0.1:{port}"
                ws = websocket.WebSocket()
                ws.connect(ws_url, timeout=1)
                ws.close()
                
                
                self.ws = websocket.WebSocketApp(
                    ws_url,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close
                )
                threading.Thread(target=self.ws.run_forever, daemon=True).start()
                return True
            except:
                continue
        return False
    
    async def get_media_info_fast(self):
        """Быстрое получение информации через Windows Media Manager"""
        try:
            sessions = await MediaManager.request_async()
            session = sessions.get_current_session()
            if session:
                info = await session.try_get_media_properties_async()
                timeline = session.get_timeline_properties()
                playback = session.get_playback_info()
                
                if info and info.artist and info.title:
                    return {
                        'artist': info.artist,
                        'title': info.title,
                        'position': timeline.position.total_seconds() if timeline.position else 0,
                        'is_playing': playback.playback_status == 4, 
                        'playback_status': playback.playback_status
                    }
        except:
            pass
        return None
    
    def update_rpc_fast(self):
        """Быстрое обновление RPC"""
        last_track_key = None
        last_playback_state = None
        last_position_update = 0
        
        while True:
            current_time = time.time()
            
            if not self.rpc:
                self.connect_rpc()
                time.sleep(3)
                continue
            
            try:
                
                media = asyncio.run(self.get_media_info_fast())
                
                if media:
                    track_key = f"{media['artist']} - {media['title']}"
                    is_playing = media['is_playing']
                    position = media['position']
                    
                    
                    track_changed = track_key != last_track_key
                    playback_changed = is_playing != last_playback_state
                    position_changed = abs(position - last_position_update) > 2  
                    
                    if track_changed or playback_changed or position_changed:
                        
                        if track_changed:
                            track = self.find_track_fast(media['artist'], media['title'])
                            if track:
                                last_track_key = track_key
                                self.track_duration = track.duration_ms // 1000
                                print(f"🎵 {media['artist']} - {media['title']}")
                            else:
                                track = None
                        else:
                            
                            track = self.track_cache.get(f"{media['artist']}|{media['title']}")
                        
                        if track:
                            track_id = track.trackId.split(":")
                            cover = f"https://{track.og_image[:-2]}400x400"
                            album = track.albums[0].title if track.albums else ""
                            artists = ", ".join(track.artists_name())
                            
                            if is_playing:
                                
                                start_time = int(current_time - position)
                                end_time = start_time + self.track_duration
                                
                                time_text = f"{self.format_time(position)} / {self.format_time(self.track_duration)}"
                                large_text = f"{album} | {time_text}" if album else time_text
                                
                                self.rpc.update(
                                    details=track.title,
                                    state=artists,
                                    large_image=cover,
                                    large_text=large_text,
                                    start=start_time,
                                    end=end_time,
                                    small_image="https://raw.githubusercontent.com/FozerG/WinYandexMusicRPC/main/assets/Playing.png",
                                    small_text="Играет"
                                )
                                
                                if playback_changed:
                                    print(f"Воспроизведение: {time_text}")
                                
                            else:
                                
                                time_text = f"{self.format_time(position)} / {self.format_time(self.track_duration)}"
                                large_text = f"{album} |  ПАУЗА | {time_text}" if album else f" ПАУЗА | {time_text}"
                                
                                self.rpc.update(
                                    details=track.title,
                                    state=artists,
                                    large_image=cover,
                                    large_text=large_text,
                                    small_image="https://raw.githubusercontent.com/FozerG/WinYandexMusicRPC/main/assets/Paused.png",
                                    small_text=f" Пауза | {time_text}"
                                )
                                
                                if playback_changed:
                                    print(f" Пауза: {time_text}")
                            
                            last_playback_state = is_playing
                            last_position_update = position
                            
                        else:
                            
                            time_text = f"{self.format_time(position)} / {self.format_time(self.track_duration)}" if self.track_duration > 0 else ""
                            
                            if is_playing:
                                self.rpc.update(
                                    details=media['title'],
                                    state=media['artist'],
                                    large_image="yandex_music",
                                    large_text=time_text if time_text else "Яндекс Музыка",
                                    small_image="https://raw.githubusercontent.com/FozerG/WinYandexMusicRPC/main/assets/Playing.png",
                                    small_text="▶ Играет"
                                )
                            else:
                                self.rpc.update(
                                    details=media['title'],
                                    state=media['artist'],
                                    large_image="yandex_music",
                                    large_text=f"⏸ ПАУЗА | {time_text}" if time_text else "⏸ ПАУЗА",
                                    small_image="https://raw.githubusercontent.com/FozerG/WinYandexMusicRPC/main/assets/Paused.png",
                                    small_text=f"⏸ Пауза | {time_text}" if time_text else "⏸ Пауза"
                                )
                            
                            last_playback_state = is_playing
                            last_position_update = position
                    
                    
                    time.sleep(0.5)
                    
                else:
                    
                    if last_track_key is not None:
                        print("Нет трека")
                        last_track_key = None
                        last_playback_state = None
                        self.rpc.clear()
                    
                    time.sleep(1)
                    
            except pypresence.exceptions.PipeClosed:
                print("Discord закрыт, ожидание...")
                self.rpc = None
                last_track_key = None
                time.sleep(3)
            except pypresence.exceptions.DiscordNotFound:
                print("Discord не запущен")
                self.rpc = None
                time.sleep(5)
            except Exception as e:
                print(f"Ошибка: {e}")
                time.sleep(1)
    
    def start(self):
        print("=" * 50)
        print("SimpleYandexMusicRPC by chereau1")
        print("=" * 50)
        
        
        if self.connect_websocket():
            print("Используется WebSocket для обновлений")
        
        print("Ожидание трека из Яндекс Музыки...")
        print("  Нажмите Ctrl+C для выхода")
        print("=" * 50)
        
        
        rpc_thread = threading.Thread(target=self.update_rpc_fast, daemon=True)
        rpc_thread.start()
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nЗавершение работы...")
            if self.rpc:
                self.rpc.close()
            if self.ws:
                self.ws.close()

if __name__ == "__main__":
    rpc = FastYandexRPC()
    rpc.start()