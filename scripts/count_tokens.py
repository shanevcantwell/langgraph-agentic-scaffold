import argparse
import sys
import os
import glob

try:
    import sentencepiece as spm
except ImportError:
    spm = None  # fallback to simple whitespace split

def load_sp_model(model_path: str):
    """Load a SentencePiece model. If unavailable, return None."""
    if not os.path.isfile(model_path):
        sys.stderr.write(f"Warning: SentencePiece model '{model_path}' not found. Falling back to whitespace tokenization.\n")
        return None
    processor = spm.SentencePieceProcessor()
    processor.load(model_path)
    return processor

def count_tokens(text: str, processor):
    """Count tokens using the given SentencePiece processor or fallback."""
    if processor is None:
        # simple split on whitespace as a rough token estimate
        return len(text.split())
    return processor.encode_as_ids(text).__len__()

def process_file(filepath: str, processor):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        token_count = count_tokens(content, processor)
        return token_count
    except Exception as e:
        sys.stderr.write(f"Error reading '{filepath}': {e}\n")
        return 0

def main():
    parser = argparse.ArgumentParser(
        description="Count tokens in text files using SentencePiece (or whitespace fallback)."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="File path(s) or glob patterns. If omitted, reads from stdin."
    )
    parser.add_argument(
        "-R",
        "--recursive",
        action="store_true",
        help="Enable recursive glob expansion (e.g., '**/*.txt')."
    )
    parser.add_argument(
        "--model",
        default="spm.model",
        help="Path to a SentencePiece model file. Defaults to 'spm.model' in the script directory."
    )

    args = parser.parse_args()

    # Load SentencePiece model if available
    processor = None
    if spm is not None:
        processor = load_sp_model(args.model)

    total_tokens = 0

    if not args.paths:
        # Read from stdin
        content = sys.stdin.read()
        token_count = count_tokens(content, processor)
        print(f"STDIN: {token_count} tokens")
        total_tokens += token_count
    else:
        # Expand each path/glob pattern
        for pattern in args.paths:
            if args.recursive:
                matched = glob.glob(pattern, recursive=True)
            else:
                matched = glob.glob(pattern)

            if not matched:
                sys.stderr.write(f"Warning: No files matched pattern '{pattern}'.\n")
                continue

            for filepath in matched:
                if os.path.isdir(filepath):
                    # Skip directories unless -R is set and they contain files via glob
                    continue
                token_count = process_file(filepath, processor)
                print(f"{filepath}: {token_count} tokens")
                total_tokens += token_count

    print(f"Total: {total_tokens} tokens")

if __name__ == "__main__":
    main()