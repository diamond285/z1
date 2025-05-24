import os
import uuid
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL",
                         "postgresql+psycopg2://postgres.akodbsqofninasbpqxbx:HgO3lFR752WPNGN@aws-0-us-east-2.pooler.supabase.com:6543/postgres")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class BlockAreaDB(Base):
    __tablename__ = "block_areas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    longitude = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    radius = Column(Float, nullable=False)


Base.metadata.create_all(bind=engine)


class BlockArea(BaseModel):
    id: Optional[str] = None
    name: str
    longitude: float
    latitude: float
    radius: float

    class Config:
        from_attributes = True


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/api/block-area/", response_model=BlockArea)
async def register_block_area(area: BlockArea, db: Session = Depends(get_db)):
    # Validate coordinates
    if not (-90 <= area.latitude <= 90):
        raise HTTPException(status_code=400, detail="Latitude must be between -90 and 90")
    if not (-180 <= area.longitude <= 180):
        raise HTTPException(status_code=400, detail="Longitude must be between -180 and 180")
    if area.radius <= 0:
        raise HTTPException(status_code=400, detail="Radius must be positive")

    db_area = BlockAreaDB(
        id=uuid.uuid4(),
        name=area.name,
        longitude=area.longitude,
        latitude=area.latitude,
        radius=area.radius
    )

    db.add(db_area)
    db.commit()
    db.refresh(db_area)

    return BlockArea(
        id=str(db_area.id),
        name=db_area.name,
        longitude=db_area.longitude,
        latitude=db_area.latitude,
        radius=db_area.radius
    )


@app.get("/api/block-area/", response_model=List[BlockArea])
async def get_block_areas(db: Session = Depends(get_db)):
    areas = db.query(BlockAreaDB).all()
    return [
        BlockArea(
            id=str(area.id),
            name=area.name,
            longitude=area.longitude,
            latitude=area.latitude,
            radius=area.radius
        ) for area in areas
    ]


@app.get("/api/block-area/{area_id}", response_model=BlockArea)
async def get_block_area(area_id: str, db: Session = Depends(get_db)):
    try:
        area = db.query(BlockAreaDB).filter(BlockAreaDB.id == uuid.UUID(area_id)).first()
        if not area:
            raise HTTPException(status_code=404, detail="Block area not found")
        return BlockArea(
            id=str(area.id),
            name=area.name,
            longitude=area.longitude,
            latitude=area.latitude,
            radius=area.radius
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
