"""A8: no user reads or writes another patient's data (permissions.py against the test database)."""
import uuid

import pytest

from app.auth import load_user
from app.errors import ApiError
from app.permissions import require_assigned_doctor, require_patient_access, require_role
from conftest import assign, new_user

pytestmark = pytest.mark.db


@pytest.fixture
def people(conn, db):
    p1, p2 = new_user(conn, "patient"), new_user(conn, "patient")
    doc, other_doc, old_doc = (new_user(conn, "doctor") for _ in range(3))
    admin = new_user(conn, "admin")
    assign(conn, doc, p1)
    assign(conn, old_doc, p1, status="ended")
    u = {k: load_user(db, v) for k, v in dict(p1=p1, p2=p2, doc=doc, other_doc=other_doc,
                                               old_doc=old_doc, admin=admin).items()}
    return u


def allowed(fn, *args, **kw) -> bool:
    try:
        fn(*args, **kw)
        return True
    except ApiError as e:
        assert (e.status, e.code) == (403, "forbidden")
        return False


@pytest.mark.parametrize("who,target,write,expected", [
    ("p1", "p1", False, True), ("p1", "p1", True, True),          # own data
    ("p1", "p2", False, False), ("p1", "p2", True, False),        # another patient
    ("doc", "p1", False, True), ("doc", "p1", True, False),       # assigned doctor: read only
    ("doc", "p2", False, False),                                  # not assigned
    ("other_doc", "p1", False, False),                            # unrelated doctor
    ("old_doc", "p1", False, False),                              # ended assignment
    ("admin", "p1", False, False),                                # admin: no patient data via the API
])
def test_patient_access_matrix(db, people, who, target, write, expected):
    assert allowed(require_patient_access, db, people[who], people[target].id, write=write) is expected


def test_unknown_patient_gets_same_403_as_forbidden(db, people):
    assert allowed(require_patient_access, db, people["doc"], uuid.uuid4()) is False
    assert allowed(require_patient_access, db, people["p1"], uuid.uuid4()) is False


@pytest.mark.parametrize("who,expected", [("doc", True), ("other_doc", False), ("old_doc", False),
                                          ("p1", False), ("admin", False)])
def test_doctor_owned_resources_need_active_assignment(db, people, who, expected):
    assert allowed(require_assigned_doctor, db, people[who], people["p1"].id) is expected


def test_require_role(people):
    assert allowed(require_role, people["doc"], "doctor")
    assert not allowed(require_role, people["p1"], "doctor")
