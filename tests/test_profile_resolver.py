from pathlib import Path

from backend.profile_resolver import DemoProfileResolver, resolve_demo_profiles_path, load_demo_profiles


def test_demo_profile_resolver_returns_openai_profile_case_insensitive():
    resolver = DemoProfileResolver()

    resolution = resolver.resolve("openai")

    assert resolution.resolved is True
    assert resolution.display_name == "OpenAI"
    assert resolution.source == "demo_profile"
    assert resolution.profile is not None
    assert "large language models" in resolution.profile.lower()


def test_demo_profile_resolver_uses_expander_for_unknown_name():
    class FakeExpander:
        def expand(self, query: str):
            assert query == "Acme Robotics"
            return ("Acme Robotics", "We build robotics systems for industrial automation across Europe.")

    resolver = DemoProfileResolver(expander=FakeExpander())

    resolution = resolver.resolve("Acme Robotics")

    assert resolution.resolved is True
    assert resolution.display_name == "Acme Robotics"
    assert resolution.source == "llm_expansion"
    assert resolution.profile == "We build robotics systems for industrial automation across Europe."


def test_demo_profile_resolver_returns_unresolved_without_expander():
    resolver = DemoProfileResolver()

    resolution = resolver.resolve("Acme Robotics")

    assert resolution.resolved is False
    assert resolution.source == "unresolved"
    assert resolution.profile is None
    assert "Add one or two sentences" in resolution.message


def test_demo_profiles_uses_explicit_path_override(monkeypatch, tmp_path):
    override_file = tmp_path / "DEMO-PROFILES.md"
    override_file.write_text(
        """
## 1. Acme Demo

**Description:**
A fictional company building practical software tooling.

**Expected matches:**
Grants for digital technology.
"""
    )

    monkeypatch.setenv("DEMO_PROFILES_PATH", str(override_file))

    profiles = load_demo_profiles(resolve_demo_profiles_path())

    assert "acme demo" in profiles


def test_resolve_demo_profiles_path_uses_fallback_when_no_candidates(monkeypatch, tmp_path):
    monkeypatch.delenv("DEMO_PROFILES_PATH", raising=False)
    monkeypatch.chdir(tmp_path)

    # Force all candidate files to appear missing so fallback is exercised.
    monkeypatch.setattr("pathlib.Path.exists", lambda _self: False, raising=False)

    assert resolve_demo_profiles_path() == tmp_path / "DEMO-PROFILES.md"


def test_resolved_query_message_is_stable_when_unresolved():
    resolver = DemoProfileResolver()

    resolution = resolver.resolve("Acme Robotics")

    assert resolution.resolved is False
    assert resolution.message == (
        "Could not expand company name automatically. Add one or two sentences about what the company does."
    )
