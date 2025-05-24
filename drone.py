import asyncio
import json
from fastapi import FastAPI, WebSocket
from pydantic import BaseModel, Field
import uvicorn

app = FastAPI(title="Drone Emulator API")

# Drone state model
class DroneState:
    def __init__(self):
        self.is_flying = False
        self.latitude = 0.0  # degrees, [-90, 90]
        self.longitude = 0.0  # degrees, [-180, 180]
        self.altitude = 0.0  # meters
        self.speed = 0.0  # m/s
        self.battery = 100.0  # percentage
        self.moving_to_target = False
        self.target_latitude = 0.0
        self.target_longitude = 0.0
        self.target_altitude = 0.0
        self.movement_speed = 5.0  # m/s

    def update_position(self, dlat=0.0, dlon=0.0, dalt=0.0):
        if self.is_flying:
            self.latitude += dlat
            self.longitude += dlon
            self.altitude += dalt
            # Approximate distance (1 degree ≈ 111,000 meters at equator)
            distance = ((dlat * 111000) ** 2 + (dlon * 111000) ** 2 + dalt ** 2) ** 0.5
            self.speed = distance / 0.1  # Speed based on displacement over 0.1s
            self.battery -= 0.01  # Simulate battery drain

    def start_move_to(self, lat, lon, alt):
        if self.is_flying:
            self.target_latitude = lat
            self.target_longitude = lon
            self.target_altitude = alt
            self.moving_to_target = True

    def update_movement(self, dt=0.1):
        if not self.is_flying or not self.moving_to_target:
            return

        # Calculate distance to target (1 degree ≈ 111,000 meters)
        dlat = self.target_latitude - self.latitude
        dlon = self.target_longitude - self.longitude
        dalt = self.target_altitude - self.altitude
        distance = ((dlat * 111000) ** 2 + (dlon * 111000) ** 2 + dalt ** 2) ** 0.5

        # If close enough, snap to target and stop
        if distance < 0.1:  # Less than 10 cm
            self.latitude = self.target_latitude
            self.longitude = self.target_longitude
            self.altitude = self.target_altitude
            self.moving_to_target = False
            self.speed = 0.0
            return

        # Calculate step size based on speed (m/s) and time step (0.1s)
        step_distance = self.movement_speed * dt  # Meters per step
        step_ratio = min(step_distance / max(distance, 0.0001), 1.0)  # Avoid division by zero

        # Interpolate position
        dlat_step = dlat * step_ratio
        dlon_step = dlon * step_ratio
        dalt_step = dalt * step_ratio

        self.latitude += dlat_step
        self.longitude += dlon_step
        self.altitude += dalt_step
        self.speed = step_distance / dt  # Update speed
        self.battery -= 0.01  # Simulate battery drain

# Request models
class MoveRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    altitude: float = Field(..., ge=0)

class MoveToRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    altitude: float = Field(..., ge=0)

# Global drone state
drone = DroneState()

# WebSocket endpoint for real-time telemetry
@app.websocket("/api/drone/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            telemetry = {
                "latitude": drone.latitude,
                "longitude": drone.longitude,
                "altitude": drone.altitude,
                "speed": drone.speed,
                "battery": drone.battery,
                "is_flying": drone.is_flying,
                "moving_to_target": drone.moving_to_target,
                "target_latitude": drone.target_latitude,
                "target_longitude": drone.target_longitude,
                "target_altitude": drone.target_altitude
            }
            await websocket.send_json(telemetry)
            await asyncio.sleep(0.1)  # Update every 0.1 seconds
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()

# REST API to control the drone
@app.post("/api/drone/takeoff")
async def takeoff(altitude: float = 10.0):
    if not drone.is_flying:
        drone.is_flying = True
        drone.altitude = altitude
        return {"status": "success", "message": f"Drone took off to {altitude} meters"}
    return {"status": "error", "message": "Drone is already flying"}

@app.post("/api/drone/land")
async def land():
    if drone.is_flying:
        drone.is_flying = False
        drone.altitude = 0.0
        drone.speed = 0.0
        drone.moving_to_target = False
        return {"status": "success", "message": "Drone landed"}
    return {"status": "error", "message": "Drone is not flying"}

@app.post("/api/drone/move")
async def move(move: MoveRequest):
    if drone.is_flying:
        drone.update_position(move.latitude, move.longitude, move.altitude)
        return {
            "status": "success",
            "message": f"Moved to lat: {drone.latitude}, lon: {drone.longitude}, alt: {drone.altitude}"
        }
    return {"status": "error", "message": "Drone is not flying"}

@app.post("/api/drone/move_to")
async def move_to(move_to: MoveToRequest):
    if drone.is_flying:
        drone.start_move_to(move_to.latitude, move_to.longitude, move_to.altitude)
        return {
            "status": "success",
            "message": f"Drone moving to lat: {move_to.latitude}, lon: {move_to.longitude}, alt: {move_to.altitude}"
        }
    return {"status": "error", "message": "Drone is not flying"}

@app.get("/api/drone/status")
async def get_status():
    return {
        "is_flying": drone.is_flying,
        "latitude": drone.latitude,
        "longitude": drone.longitude,
        "altitude": drone.altitude,
        "speed": drone.speed,
        "battery": drone.battery,
        "moving_to_target": drone.moving_to_target,
        "target_latitude": drone.target_latitude,
        "target_longitude": drone.target_longitude,
        "target_altitude": drone.target_altitude
    }

# Background task to simulate drone movement
async def simulate_drone():
    while True:
        if drone.is_flying:
            if drone.moving_to_target:
                drone.update_movement(dt=0.1)
            else:
                # Simulate slight movement when not targeting (0.0001 degrees ≈ 11 meters)
                drone.update_position(dlat=0.0001, dlon=0.0001, dalt=0.0)
        await asyncio.sleep(0.1)

# Start the background simulation
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(simulate_drone())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)