from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.safety import Site
from app.schemas.sites import SiteCreate, SiteOut

router = APIRouter(prefix="/sites", tags=["sites"])


@router.post("", status_code=201, response_model=SiteOut)
def create_site(payload: SiteCreate, db: Session = Depends(get_db)):
    site = Site(name=payload.name, location=payload.location)
    db.add(site)
    db.commit()
    db.refresh(site)
    return site


@router.get("", response_model=list[SiteOut])
def list_sites(db: Session = Depends(get_db)):
    return db.query(Site).all()
