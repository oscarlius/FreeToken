import os
import unittest
from unittest.mock import patch

from scripts.ssh_credentials import SSHConfigurationError, ssh_connect_kwargs


class SSHCredentialsTests(unittest.TestCase):
    def test_missing_host_and_user_reports_the_required_names(self):
        with self.assertRaisesRegex(
            SSHConfigurationError, "FT_SSH_HOST.*FT_SSH_USER"
        ):
            ssh_connect_kwargs({})

    def test_reads_required_settings_from_the_environment(self):
        with patch.dict(
            os.environ,
            {
                "FT_SSH_HOST": "test-host",
                "FT_SSH_USER": "test-user",
                "FT_SSH_PASSWORD": "test-password",
            },
            clear=True,
        ):
            self.assertEqual(
                ssh_connect_kwargs(),
                {
                    "hostname": "test-host",
                    "username": "test-user",
                    "password": "test-password",
                },
            )

    def test_omitting_password_keeps_paramiko_key_auth_available(self):
        self.assertEqual(
            ssh_connect_kwargs(
                {"FT_SSH_HOST": "test-host", "FT_SSH_USER": "test-user"}
            ),
            {"hostname": "test-host", "username": "test-user"},
        )


if __name__ == "__main__":
    unittest.main()
