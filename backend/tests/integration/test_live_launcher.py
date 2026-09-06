import unittest

from scripts.run_live_backend import (
    DEFAULT_MODELS,
    build_live_environment,
    select_provider_model,
    server_command,
)


class LiveLauncherTests(unittest.TestCase):
    def test_bedrock_default_uses_structured_extraction_capable_model(self):
        self.assertEqual(DEFAULT_MODELS["bedrock"], "amazon.nova-lite-v1:0")

    def test_live_environment_preserves_process_values_and_sets_provider(self):
        environment = build_live_environment(
            {"PATH": "/synthetic/bin", "APP_MODE": "cached"},
            provider="openai",
            openai_api_key="synthetic-secret",
            model="synthetic-model",
        )

        self.assertEqual(environment["PATH"], "/synthetic/bin")
        self.assertEqual(environment["APP_MODE"], "live")
        self.assertEqual(environment["LLM_PROVIDER"], "openai")
        self.assertEqual(environment["LLM_MODEL"], "synthetic-model")
        self.assertEqual(environment["OPENAI_API_KEY"], "synthetic-secret")

    def test_explicit_provider_ignores_stale_model_from_another_provider(self):
        self.assertEqual(
            select_provider_model(
                {"LLM_PROVIDER": "bedrock", "LLM_MODEL": "amazon.stale-v1:0"},
                requested_provider="openai",
                requested_model=None,
            ),
            ("openai", DEFAULT_MODELS["openai"]),
        )

    def test_environment_model_is_kept_when_provider_is_not_overridden(self):
        self.assertEqual(
            select_provider_model(
                {"LLM_PROVIDER": "openai", "LLM_MODEL": "gpt-custom"},
                requested_provider=None,
                requested_model=None,
            ),
            ("openai", "gpt-custom"),
        )

    def test_live_environment_rejects_missing_credentials(self):
        for api_key, model in [
            ("", "model"),
            ("   ", "model"),
            ("secret", ""),
            ("secret", "   "),
        ]:
            with (
                self.subTest(api_key=bool(api_key), model=repr(model)),
                self.assertRaisesRegex(
                    ValueError, "A non-empty (OpenAI API key|model ID) is required"
                ),
            ):
                build_live_environment(
                    {},
                    provider="openai",
                    openai_api_key=api_key,
                    model=model,
                )

    def test_live_environment_selects_bedrock_and_preserves_aws_credentials(self):
        environment = build_live_environment(
            {
                "AWS_ACCESS_KEY_ID": "synthetic-access",
                "AWS_SECRET_ACCESS_KEY": "synthetic-secret",
                "AWS_SESSION_TOKEN": "synthetic-token",
            },
            provider="bedrock",
            model="amazon.synthetic-v1:0",
            aws_region="us-east-1",
        )

        self.assertEqual(environment["APP_MODE"], "live")
        self.assertEqual(environment["LLM_PROVIDER"], "bedrock")
        self.assertEqual(environment["LLM_MODEL"], "amazon.synthetic-v1:0")
        self.assertEqual(environment["AWS_REGION"], "us-east-1")
        self.assertEqual(environment["AWS_SESSION_TOKEN"], "synthetic-token")
        self.assertNotIn("OPENAI_API_KEY", environment)

    def test_live_environment_rejects_unknown_provider_or_missing_region(self):
        for provider, region in [("other", "us-east-1"), ("bedrock", "")]:
            with (
                self.subTest(provider=provider, region=repr(region)),
                self.assertRaises(ValueError),
            ):
                build_live_environment(
                    {},
                    provider=provider,
                    model="model",
                    aws_region=region,
                )

    def test_server_command_contains_no_credentials(self):
        command = server_command("/safe/python", port=8123, reload=False)

        self.assertEqual(
            command,
            (
                "/safe/python",
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8123",
            ),
        )
        self.assertNotIn("key", " ".join(command).lower())

    def test_server_command_supports_development_reload(self):
        command = server_command("python", port=8000, reload=True)

        self.assertEqual(command[-1], "--reload")

    def test_server_command_rejects_invalid_ports(self):
        for port in [0, 65536, True]:
            with (
                self.subTest(port=port),
                self.assertRaisesRegex(ValueError, "valid TCP port"),
            ):
                server_command("python", port=port, reload=False)


if __name__ == "__main__":
    unittest.main()
