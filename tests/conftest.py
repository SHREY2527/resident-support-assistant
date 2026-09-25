import os
from datetime import date

import pytest

from app import config
from app.bot import Bot
from app.data_loader import Corpus

TODAY = date(2026, 9, 25)
RESIDENT = "RES-3427"


@pytest.fixture
def corpus(tmp_path):
    return Corpus.load(config.DATA_DIR, tmp_path / "tickets_runtime.json")


@pytest.fixture
def live_bot_factory(corpus):
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set")
    from app.llm import GeminiLLM
    llm = GeminiLLM()

    def make(resident=RESIDENT):
        return Bot(resident, corpus, llm, today=TODAY)
    make.corpus = corpus
    return make
