from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.safety import Device, Site
from app.schemas.devices import DeviceCreate, DeviceOut

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("", status_code=201, response_model=DeviceOut)
def register_device(payload: DeviceCreate, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == payload.site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    device = Device(label=payload.label, site_id=payload.site_id)
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.get("", response_model=list[DeviceOut])
def list_devices(site_id: str, db: Session = Depends(get_db)):
    return db.query(Device).filter(Device.site_id == site_id).all()
