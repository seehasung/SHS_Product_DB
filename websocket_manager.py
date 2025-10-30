# websocket_manager.py

from fastapi import WebSocket
from typing import Dict, List
import json

class ConnectionManager:
    """WebSocket 연결 관리자"""
    
    def __init__(self):
        # user_id를 키로 하는 WebSocket 연결 딕셔너리
        self.active_connections: Dict[int, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: int):
        """클라이언트 연결"""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        print(f"✅ WebSocket 연결: user_id={user_id}, 총 연결={len(self.active_connections[user_id])}")
    
    def disconnect(self, websocket: WebSocket, user_id: int):
        """클라이언트 연결 해제"""
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            if len(self.active_connections[user_id]) == 0:
                del self.active_connections[user_id]
        print(f"❌ WebSocket 연결 해제: user_id={user_id}")
    
    async def send_personal_message(self, message: dict, user_id: int):
        """특정 사용자에게 메시지 전송"""
        if user_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except:
                    disconnected.append(connection)
            
            # 끊어진 연결 제거
            for conn in disconnected:
                self.active_connections[user_id].remove(conn)
    
    async def broadcast(self, message: dict):
        """모든 연결된 클라이언트에게 메시지 전송"""
        for user_id, connections in self.active_connections.items():
            for connection in connections:
                try:
                    await connection.send_json(message)
                except:
                    pass

# 전역 ConnectionManager 인스턴스
manager = ConnectionManager()