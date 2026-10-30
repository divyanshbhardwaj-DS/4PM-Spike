import uvicorn

if __name__ == "__main__":
    print("=" * 70)
    print("  DSS-1.0 — Campus Energy Decision Support System")
    print("  AI Synergy Hackathon 2026 — Case 05: The 4 PM Spike")
    print("  Offline-first, Deterministic, Advisory-Only Intelligence Platform")
    print("=" * 70)
    print("  Public Portal:         http://localhost:8000/")
    print("  Electrician Login:     http://localhost:8000/login/electrician")
    print("  Management Login:      http://localhost:8000/login/management")
    print("  Interactive API Docs:  http://localhost:8000/docs")
    print("=" * 70)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)

