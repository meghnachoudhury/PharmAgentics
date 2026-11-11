"""Regression guard: the live Briefing frontend contains no fictitious prototypes."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "figma-make" / "src"


def test_frontend_contains_only_supported_feature_modules():
    assert SRC.is_dir()
    assert sorted(p.relative_to(SRC).as_posix() for p in SRC.rglob("*") if p.is_file()) == [
        "App.tsx", "agent/briefingApi.ts", "agent/primitives.tsx", "index.css", "main.tsx", "vite-env.d.ts"
    ]


def test_live_frontend_no_mock_fallback_or_fake_review():
    app = (SRC / "App.tsx").read_text()
    api = (SRC / "agent" / "briefingApi.ts").read_text()
    for s in ["mockAgentService", "mockService", "SEED.runs", "sampleFixture", "sample_fixture", "offline (simulated)"]:
        assert s not in app and s not in api
    assert 'getBriefing({' in app
    assert 'getContext()' in app
    assert 'evidence_id' in app and 'data_version' in app
    assert 'throw new Error("API URL is not configured' in api
