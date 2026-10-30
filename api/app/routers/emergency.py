"""Emergency configuration, emergency card and emergency events (incident records).

PULSE never claims a call or share succeeded: actions are stored as "tapped"/"opened" with
confirmed=false. The doctor reviews incidents later; nobody is notified in real time.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from ..analysis.rules import RED_FLAG_SYMPTOMS, SEVERE_DIASTOLIC, SEVERE_SYSTOLIC
from ..auth import require_token
from ..config import DEMO_NUMBER_ID, Settings
from ..errors import AUTH_RESPONSES, not_implemented
from ..schemas import (ClientFallback, EmergencyActionsIn, EmergencyCardOut, EmergencyConfigOut,
                       EmergencyEventIn, EmergencyEventOut, EmergencyEventPatch, EmergencyNumber,
                       EmergencyReportOut)

CONFIG_VERSION = "1"
DISCLAIMER_FR = ("PULSE n'appelle pas les secours automatiquement et ne prévient pas votre médecin en temps réel. "
                 "Appuyez sur le bouton pour appeler vous-même.")
DISCLAIMER_AR = "تطبيق PULSE لا يتصل بالإسعاف تلقائياً ولا يُبلغ طبيبك فوراً. اضغط على الزر للاتصال بنفسك."

public = APIRouter(tags=["emergency"])
router = APIRouter(tags=["emergency"], responses=AUTH_RESPONSES, dependencies=[Depends(require_token)])


def build_config(settings: Settings) -> EmergencyConfigOut:
    numbers = [EmergencyNumber(**n) for n in settings.emergency_numbers]
    primary = settings.primary_number_id
    if settings.demo_mode:
        # Demo mode never points the main button at a real emergency number.
        numbers.insert(0, EmergencyNumber(
            id=DEMO_NUMBER_ID, label_fr="DÉMO — téléphone d'un membre de l'équipe",
            label_ar="تجريبي — هاتف أحد أعضاء الفريق", number=settings.demo_number or "",
            verified=False, source="Demo substitute; not an emergency service."))
        primary = DEMO_NUMBER_ID
    return EmergencyConfigOut(
        version=CONFIG_VERSION, demo_mode=settings.demo_mode, numbers=numbers, primary_number_id=primary,
        disclaimer_fr=DISCLAIMER_FR, disclaimer_ar=DISCLAIMER_AR,
        client_fallback=ClientFallback(severe_systolic=SEVERE_SYSTOLIC, severe_diastolic=SEVERE_DIASTOLIC,
                                       red_flag_symptoms=sorted(RED_FLAG_SYMPTOMS)))


@public.get("/config/emergency", response_model=EmergencyConfigOut,
            summary="Emergency numbers and offline fallback constants (no login; cache it on the device)")
def emergency_config(request: Request):
    return build_config(request.app.state.settings)


@router.get("/patients/{patient_id}/emergency-card", response_model=EmergencyCardOut,
            summary="What a bystander or responder needs; cache it for offline use")
def emergency_card(patient_id: UUID):
    not_implemented()


@router.post("/patients/{patient_id}/emergency-events", response_model=EmergencyEventOut, status_code=201,
             summary="Patient: open an emergency event; repeating the same client id returns the stored event")
def create_event(patient_id: UUID, body: EmergencyEventIn):
    not_implemented()


@router.get("/patients/{patient_id}/emergency-events", response_model=list[EmergencyEventOut])
def list_events(patient_id: UUID):
    not_implemented()


@router.post("/emergency-events/{event_id}/actions", response_model=EmergencyEventOut,
             summary="Patient: append actions; known client_action_id values are ignored")
def add_actions(event_id: UUID, body: EmergencyActionsIn):
    not_implemented()


@router.patch("/emergency-events/{event_id}", response_model=EmergencyEventOut,
              summary="Patient: location (only with consent), outcome, end time")
def patch_event(event_id: UUID, body: EmergencyEventPatch):
    not_implemented()


@router.get("/emergency-events/{event_id}/report", response_model=EmergencyReportOut,
            summary="Event, linked alert, readings and symptom reports within ±24 h")
def event_report(event_id: UUID):
    not_implemented()
