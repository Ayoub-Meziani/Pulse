from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import current_user, get_db
from ..errors import ApiError
from ..models import Alert, User
from ..permissions import require_patient_access
from ..schemas import AlertDetail

router = APIRouter(tags=["alerts"])


@router.get("/alerts/{alert_id}", response_model=AlertDetail)
def get_alert(alert_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise ApiError(404, "not_found", "Alert not found.")
    require_patient_access(db, user, alert.patient_id)
    return alert
