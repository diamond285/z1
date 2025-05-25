from fastapi import FastAPI, WebSocket, HTTPException
from pydantic import BaseModel
from typing import List, Dict
import httpx
import asyncio
import json
from sqlalchemy import create_engine, Column, Integer, String, Numeric, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
from datetime import datetime

app = FastAPI(title="Drone Controller API")

DATABASE_URL = "postgresql+psycopg2://postgres.akodbsqofninasbpqxbx:HgO3lFR752WPNGN@aws-0-us-east-2.pooler.supabase.com:6543/postgres"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Drone(Base):
    __tablename__ = "drones"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    owner_id = Column(Integer, nullable=False)
    current_lat = Column(Numeric(10, 8))
    current_lng = Column(Numeric(11, 8))
    current_altitude = Column(Numeric(8, 2))
    current_status = Column(String(50), default="stopped")
    battery_level = Column(Integer, default=100)
    max_speed = Column(Numeric(6, 2), default=50.0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    ip = Column(String(100))
    port = Column(String(10))

Base.metadata.create_all(bind=engine)

websocket_connections: List[WebSocket] = []

class MoveRequest(BaseModel):
    longitude: float
    latitude: float
    altitude: float

class DroneRegisterRequest(BaseModel):
    name: str
    owner_id: int
    ip: str
    port: str
    max_speed: float = 50.0

def get_drone_url(drone_id: int, db):
    drone = db.query(Drone).filter(Drone.id == drone_id).first()
    if not drone:
        raise HTTPException(status_code=404, detail=f"Drone {drone_id} not found")
    return f"http://{drone.ip}:{drone.port}"

async def send_to_drone(drone_id: int, endpoint: str, method: str = "POST", data: dict = None):
    db = SessionLocal()
    try:
        drone_url = get_drone_url(drone_id, db)
        async with httpx.AsyncClient() as client:
            try:
                if method == "POST":
                    response = await client.post(f"{drone_url}{endpoint}", json=data)
                elif method == "GET":
                    response = await client.get(f"{drone_url}{endpoint}")
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                raise HTTPException(status_code=e.response.status_code, detail=str(e))
            except httpx.RequestError as e:
                raise HTTPException(status_code=500, detail=f"Failed to communicate with drone {drone_id}: {str(e)}")
    finally:
        db.close()

@app.post("/api/drones/register")
async def register_drone(drone: DroneRegisterRequest):
    db = SessionLocal()
    try:
        db_drone = Drone(
            name=drone.name,
            owner_id=drone.owner_id,
            ip=drone.ip,
            port=drone.port,
            max_speed=drone.max_speed
        )
        db.add(db_drone)
        db.commit()
        db.refresh(db_drone)
        return {"drone_id": db_drone.id, "status": "drone registered", "details": {
            "name": db_drone.name,
            "owner_id": db_drone.owner_id,
            "ip": db_drone.ip,
            "port": db_drone.port,
            "max_speed": db_drone.max_speed
        }}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to register drone: {str(e)}")
    finally:
        db.close()

@app.post("/api/drones/{drone_id}/takeoff")
async def takeoff_drone(drone_id: int):
    result = await send_to_drone(drone_id, "/api/drone/takeoff")
    db = SessionLocal()
    try:
        db.query(Drone).filter(Drone.id == drone_id).update({"current_status": "flying", "updated_at": func.now()})
        db.commit()
        return {"drone_id": drone_id, "status": "takeoff initiated", "result": result}
    finally:
        db.close()

@app.post("/api/drones/{drone_id}/land")
async def land_drone(drone_id: int):
    result = await send_to_drone(drone_id, "/api/drone/land")
    db = SessionLocal()
    try:
        db.query(Drone).filter(Drone.id == drone_id).update({"current_status": "stopped", "updated_at": func.now()})
        db.commit()
        return {"drone_id": drone_id, "status": "landing initiated", "result": result}
    finally:
        db.close()

@app.post("/api/drones/{drone_id}/move")
async def move_drone(drone_id: int, move: MoveRequest):
    result = await send_to_drone(drone_id, "/api/drone/move", data=move.dict())
    db = SessionLocal()
    try:
        db.query(Drone).filter(Drone.id == drone_id).update({
            "current_lat": move.latitude,
            "current_lng": move.longitude,
            "current_altitude": move.altitude,
            "updated_at": func.now()
        })
        db.commit()
        return {"drone_id": drone_id, "status": "move command sent", "result": result}
    finally:
        db.close()

@app.post("/api/drones/{drone_id}/move_to")
async def move_to_drone(drone_id: int, move: MoveRequest):
    result = await send_to_drone(drone_id, "/api/drone/move_to", data=move.dict())
    db = SessionLocal()
    try:
        db.query(Drone).filter(Drone.id == drone_id).update({
            "current_lat": move.latitude,
            "current_lng": move.longitude,
            "current_altitude": move.altitude,
            "updated_at": func.now()
        })
        db.commit()
        return {"drone_id": drone_id, "status": "move_to command sent", "result": result}
    finally:
        db.close()

@app.get("/api/drones/{drone_id}/status")
async def get_drone_status(drone_id: int):
    result = await send_to_drone(drone_id, "/api/drone/status", method="GET")
    return {"drone_id": drone_id, "status": result}

@app.websocket("/api/drones/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await websocket.accept()
    websocket_connections.append(websocket)
    db = SessionLocal()
    try:
        while True:
            telemetry_data = {}
            drones = db.query(Drone).all()
            for drone in drones:
                try:
                    async with httpx.AsyncClient() as client:
                        response = await client.get(f"http://{drone.ip}:{drone.port}/api/drone/status")
                        response.raise_for_status()
                        telemetry_data[drone.id] = {
                            "name": drone.name,
                            "status": response.json(),
                            "current_lat": float(drone.current_lat) if drone.current_lat else None,
                            "current_lng": float(drone.current_lng) if drone.current_lng else None,
                            "current_altitude": float(drone.current_altitude) if drone.current_altitude else None,
                            "battery_level": drone.battery_level,
                            "max_speed": float(drone.max_speed)
                        }
                except httpx.HTTPError:
                    telemetry_data[drone.id] = {"error": "Failed to fetch telemetry"}
            
            for ws in websocket_connections:
                try:
                    await ws.send_json(telemetry_data)
                except:
                    websocket_connections.remove(ws)
            
            await asyncio.sleep(1)  # Update every second
    except Exception as e:
        websocket_connections.remove(websocket)
        await websocket.close()
    finally:
        db.close()