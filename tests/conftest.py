"""
pytest configuration and shared fixtures
"""

import os
import sys
from pathlib import Path
import pytest
from decimal import Decimal
from datetime import datetime, timezone

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "poller"))
sys.path.insert(0, str(project_root / "app"))


@pytest.fixture(scope="session", autouse=True)
def test_env():
    """Set up test environment variables."""
    os.environ.update(
        {
            "DB_HOST": "localhost",
            "DB_PORT": "5432",
            "DB_NAME": "test_lifecycle_tracker",
            "DB_USER": "test_user",
            "DB_PASSWORD": "test_password",
            "AWS_REGION": "ap-south-1",
            "AWS_ACCOUNT_ID": "123456789012",
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
            "SNS_TOPIC_ARN": "arn:aws:sns:ap-south-1:123456789012:test-topic",
            "S3_SNAPSHOT_BUCKET": "test-bucket",
            "DASHBOARD_PASSWORD": "test_password",
        }
    )


@pytest.fixture
def aws_credentials():
    """Mocked AWS credentials."""
    os.environ.update(
        {
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
        }
    )


@pytest.fixture
def aws_region():
    return "ap-south-1"


@pytest.fixture
def aws_account_id():
    return "123456789012"


@pytest.fixture
def boto3_session(aws_credentials, aws_region):
    """Real boto3 session (for use with moto)."""
    import boto3

    return boto3.Session(region_name=aws_region)


@pytest.fixture
def flask_app():
    """Flask app in testing mode."""
    from app.main import app

    app.config.update({"TESTING": True, "DEBUG": False})
    return app


@pytest.fixture
def flask_client(flask_app):
    """Flask test client."""
    return flask_app.test_client()


@pytest.fixture
def authenticated_client(flask_client):
    """Flask test client with HTTP Basic Auth."""
    from base64 import b64encode

    credentials = b64encode(b"admin:test_password").decode("utf-8")
    flask_client.environ_base["HTTP_AUTHORIZATION"] = f"Basic {credentials}"
    return flask_client
