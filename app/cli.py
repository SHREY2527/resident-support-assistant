import argparse

from . import config
from .bot import Bot
from .data_loader import Corpus
from .llm import GeminiLLM


def main() -> None:
    ap = argparse.ArgumentParser(description="Resident Support Assistant")
    ap.add_argument("--resident", required=True, help="Logged-in resident ID (session identity, e.g. RES-3427)")
    args = ap.parse_args()
    corpus = Corpus.load(config.DATA_DIR, config.RUNTIME_TICKETS)
    if args.resident not in corpus.known_resident_ids():
        print(f"(note: {args.resident} has no tickets in the sample data)")
    bot = Bot(args.resident, corpus, GeminiLLM())
    print(f"Resident Support Assistant (signed in as {args.resident}). Type 'quit' to exit.\n")
    while True:
        try:
            msg = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if msg.lower() in {"quit", "exit"}:
            break
        if msg:
            try:
                reply = bot.handle(msg)
                print(f"\nBot: {reply.text}\n")
                if reply.usage:
                    print(f"[usage] {reply.usage}\n")
            except Exception as e:
                print(f"\nBot: Sorry, something went wrong. Please try again. (error: {e})\n")


if __name__ == "__main__":
    main()
