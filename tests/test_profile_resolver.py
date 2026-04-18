from backend.profile_resolver import DemoProfileResolver


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
