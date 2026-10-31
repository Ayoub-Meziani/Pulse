"""Emergency configuration, emergency card and emergency events (incident records).

PULSE never claims a call or share succeeded: actions are stored as "tapped"/"opened" with
confirmed=false. Unless escalation is enabled (routers/escalation.py, clinically approved), the doctor
reviews incidents later and nobody is notified in real time. Events never change alerts, and the card
and events never include doctor notes.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import ValidationError

from ..analysis.rules import RED_FLAG_SYMPTOMS, SEVERE_DIASTOLIC, SEVERE_SYSTOLIC
from sqlalchemy.orm import Session

from ..auth import CurrentUser, current_user
from ..config import DEMO_NUMBER_ID, Settings
from ..db import require_session
from ..errors import AUTH_RESPONSES
from ..models import EmergencyEvent
from ..permissions import require_patient_access
from ..services import emergency_events as events, escalation, patient_data
from ..services.measurements import list_readings
from ..schemas import (ClientFallback, EmergencyActionsIn, EmergencyCardOut, EmergencyConfigOut,
                       EmergencyEventIn, EmergencyEventOut, EmergencyEventPatch, EmergencyNumber,
                       EmergencyReportOut, MeasurementOut, SymptomReportOut)
from .alerts import alert_out

CONFIG_VERSION = "1"
DISCLAIMER_FR = ("PULSE n'appelle pas les secours automatiquement et ne prévient pas votre médecin en temps réel. "
                 "Appuyez sur le bouton pour appeler vous-même.")
DISCLAIMER_AR = "تطبيق PULSE لا يتصل بالإسعاف تلقائياً ولا يُبلغ طبيبك فوراً. اضغط على الزر للاتصال بنفسك."
# With escalation on (clinically approved), the doctor gets an in-app notification; nothing else changes.
ESCALATION_DISCLAIMER_FR = ("PULSE n'appelle pas les secours et ne prévient pas vos proches automatiquement. "
                            "Votre médecin reçoit une notification dans l'application, sans garantie qu'il la voie "
                            "à temps. Appuyez sur le bouton pour appeler vous-même.")
ESCALATION_DISCLAIMER_AR = ("تطبيق PULSE لا يتصل بالإسعاف ولا يُبلغ أقاربك تلقائياً. يتلقى طبيبك إشعاراً داخل التطبيق "
                            "دون ضمان أن يراه في الوقت المناسب. اضغط على الزر للاتصال بنفسك.")

public = APIRouter(tags=["emergency"])
router = APIRouter(tags=["emergency"], responses=AUTH_RESPONSES, dependencies=[Depends(current_user)])


def build_config(settings: Settings) -> EmergencyConfigOut:
    """Built once at startup (create_app), so a broken configuration stops the app instead of
    breaking the emergency screen at the moment someone needs it."""
    try:
        numbers = [EmergencyNumber(**n) for n in settings.emergency_numbers]
    except (TypeError, ValidationError) as exc:
        raise RuntimeError(f"Invalid PULSE_EMERGENCY_NUMBERS entry: {exc}") from exc
    primary = settings.primary_number_id
    if settings.demo_mode:
        if settings.env != "dev" and not settings.demo_number:
            raise RuntimeError("Set PULSE_DEMO_NUMBER (a teammate's phone) when PULSE_DEMO_MODE is on.")
        # Demo mode never points the main button at a real emergency number.
        numbers.insert(0, EmergencyNumber(
            id=DEMO_NUMBER_ID, label_fr="DÉMO — téléphone d'un membre de l'équipe",
            label_ar="تجريبي — هاتف أحد أعضاء الفريق", number=settings.demo_number or None,
            verified=False, source="Demo substitute; not an emergency service."))
        primary = DEMO_NUMBER_ID
    ids = [n.id for n in numbers]
    if len(ids) != len(set(ids)):
        raise RuntimeError(f"Duplicate emergency number ids: {ids}")
    chosen = next((n for n in numbers if n.id == primary), None)
    if chosen is None:
        raise RuntimeError(f"PULSE_PRIMARY_NUMBER_ID={primary!r} matches none of {ids}")
    if not settings.demo_mode and not chosen.number:
        raise RuntimeError(f"Primary emergency number {primary!r} has no number.")
    return EmergencyConfigOut(
        version=CONFIG_VERSION, demo_mode=settings.demo_mode, numbers=numbers, primary_number_id=primary,
        disclaimer_fr=ESCALATION_DISCLAIMER_FR if settings.escalation_enabled else DISCLAIMER_FR,
        disclaimer_ar=ESCALATION_DISCLAIMER_AR if settings.escalation_enabled else DISCLAIMER_AR,
        escalation_enabled=settings.escalation_enabled,
        client_fallback=ClientFallback(severe_systolic=SEVERE_SYSTOLIC, severe_diastolic=SEVERE_DIASTOLIC,
                                       red_flag_symptoms=sorted(RED_FLAG_SYMPTOMS)))


@public.get("/config/emergency", response_model=EmergencyConfigOut,
            summary="Emergency numbers and offline fallback constants (no login; cache it on the device)")
def emergency_config(request: Request):
    return request.app.state.emergency_config


@router.get("/patients/{patient_id}/emergency-card", response_model=EmergencyCardOut,
            summary="What a bystander or responder needs; cache it for offline use")
def emergency_card(patient_id: UUID, request: Request, user: CurrentUser = Depends(current_user),
                   db: Session = Depends(require_session)):
    # Minimum for emergency support: no doctor notes, no M6 risk factors, no wearable data.
    require_patient_access(db, user, patient_id)
    return patient_data.emergency_card(db, patient_id, request.app.state.clock())


@router.post("/patients/{patient_id}/emergency-events", response_model=EmergencyEventOut, status_code=201,
             summary="Patient: open an emergency event; repeating the same client id returns the stored event",
             responses={200: {"model": EmergencyEventOut,
                              "description": "An event with this client-generated id already exists; it is returned unchanged (safe retry)."},
                        201: {"description": "Event created."}})
def create_event(patient_id: UUID, body: EmergencyEventIn, request: Request, response: Response,
                 user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    require_patient_access(db, user, patient_id, write=True)
    now = request.app.state.clock()
    event, created = events.create_event(db, user, body, now)
    if created:  # the escalation decision is made once, on the server, from stored evidence
        event = escalation.start(db, event, request.app.state.settings.escalation_enabled, now)
    else:
        response.status_code = 200
    return events.event_out(event)


@router.get("/patients/{patient_id}/emergency-events", response_model=list[EmergencyEventOut],
            summary="Emergency events, newest first (patient or assigned doctor)")
def list_events(patient_id: UUID, user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    require_patient_access(db, user, patient_id)
    return [events.event_out(e) for e in events.list_events(db, patient_id)]


def _own_event(db: Session, user: CurrentUser, event_id: UUID) -> EmergencyEvent:
    event = events.get_event(db, event_id)
    require_patient_access(db, user, event.patient_id, write=True)  # only the patient changes their event
    return events.get_event(db, event_id, lock=True)  # serialise concurrent retries of the same event


@router.post("/emergency-events/{event_id}/actions", response_model=EmergencyEventOut,
             summary="Patient: append actions; known client_action_id values are ignored")
def add_actions(event_id: UUID, body: EmergencyActionsIn, request: Request,
                user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    event = _own_event(db, user, event_id)
    return events.event_out(events.add_actions(db, event, body, request.app.state.clock()))


@router.patch("/emergency-events/{event_id}", response_model=EmergencyEventOut,
              summary="Patient: location (only with consent), outcome, end time")
def patch_event(event_id: UUID, body: EmergencyEventPatch, request: Request,
                user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    event = _own_event(db, user, event_id)
    return events.event_out(events.patch_event(db, event, body, request.app.state.clock()))


@router.get("/emergency-events/{event_id}/report", response_model=EmergencyReportOut,
            summary="Event, linked alert, readings and symptom reports within ±24 h")
def event_report(event_id: UUID, user: CurrentUser = Depends(current_user), db: Session = Depends(require_session)):
    event = events.get_event(db, event_id)
    require_patient_access(db, user, event.patient_id)
    alert, reports = events.report_context(db, event)
    window = events.REPORT_WINDOW
    readings = list_readings(db, event.patient_id, event.started_at - window, event.started_at + window,
                             1000, include_invalid=False)
    return EmergencyReportOut(
        event=events.event_out(event), alert=alert_out(alert) if alert else None,
        readings=[MeasurementOut.model_validate(m) for m in readings],
        symptom_reports=[SymptomReportOut(id=r.id, patient_id=r.patient_id, symptoms=r.symptoms, measurement_id=None,
                                          onset_at=r.onset_at, reported_at=r.reported_at, source=r.source)
                         for r in reports])
