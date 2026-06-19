"""Auth flow tests: signup, login, refresh rotation, logout, /me, error paths."""

from __future__ import annotations

PW = "Sup3r$ecret!"


def test_signup_returns_token_pair(client):
    r = client.post(
        "/api/v1/auth/signup",
        json={"email": "founder@acme.co", "password": PW, "org_name": "Acme", "full_name": "F"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["token_type"] == "bearer"


def test_signup_duplicate_email_rejected(client):
    payload = {"email": "dup@acme.co", "password": PW, "org_name": "Acme"}
    assert client.post("/api/v1/auth/signup", json=payload).status_code == 201
    r = client.post("/api/v1/auth/signup", json={**payload, "org_name": "Other"})
    assert r.status_code == 400


def test_signup_weak_password_rejected(client):
    r = client.post(
        "/api/v1/auth/signup",
        json={"email": "weak@acme.co", "password": "short", "org_name": "Acme"},
    )
    assert r.status_code == 422


def test_login_success_and_me(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "u@acme.co", "password": PW, "org_name": "Acme"},
    )
    r = client.post("/api/v1/auth/login", json={"email": "u@acme.co", "password": PW})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "u@acme.co"


def test_login_wrong_password_401_uniform(client):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "u2@acme.co", "password": PW, "org_name": "Acme"},
    )
    r = client.post("/api/v1/auth/login", json={"email": "u2@acme.co", "password": "wrongpass1"})
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Invalid credentials"


def test_login_unknown_user_401_no_enumeration(client):
    r = client.post("/api/v1/auth/login", json={"email": "ghost@acme.co", "password": PW})
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Invalid credentials"


def test_refresh_rotates_and_revokes_old(client):
    tokens = client.post(
        "/api/v1/auth/signup",
        json={"email": "r@acme.co", "password": PW, "org_name": "Acme"},
    ).json()
    rt = tokens["refresh_token"]
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
    assert r1.status_code == 200
    # The old refresh token is now revoked (rotation).
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
    assert r2.status_code == 401


def test_logout_revokes_refresh_token(client):
    tokens = client.post(
        "/api/v1/auth/signup",
        json={"email": "lo@acme.co", "password": PW, "org_name": "Acme"},
    ).json()
    rt = tokens["refresh_token"]
    assert client.post("/api/v1/auth/logout", json={"refresh_token": rt}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": rt}).status_code == 401


def test_protected_route_requires_token(client):
    assert client.get("/api/v1/leads/").status_code == 401


def test_garbage_token_rejected(client):
    r = client.get("/api/v1/leads/", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401
