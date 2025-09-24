# Audited on Sept 23, 2025
import pytest
import os
from dotenv import load_dotenv

@pytest.fixture(scope='session', autouse=True)
def load_env():
    load_dotenv()
