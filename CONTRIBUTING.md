# Contributing to imf-polarity

Thank you for your interest in improving imf-polarity. Contributions of all kinds are welcome:
bug reports, questions, documentation fixes, tests and code.

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Reporting a problem or asking for support

Open an issue on the project's public issue tracker, https://github.com/amrthabit2000-bot/imf-polarity/issues. Please include:

- the imf-polarity version (`python -c "import imf_polarity; print(imf_polarity.__version__)"`),
  your Python version and operating system;
- the exact command or code you ran, with the settings (rule, minimum hours, minimum agreement,
  years);
- the full error message, or the expected and the obtained result.

Questions about the method (the polarity rules, the quality tests, the T/A tables) are welcome as
issues too.

## Setting up a development copy

```
python -m pip install -e .[test,plot]
python -m pytest -q
```

The tests need no network connection: they build small synthetic OMNI2 files with known answers.

## Making a change

1. Open an issue first for anything larger than a small fix, so the change can be discussed.
2. Keep the computed results unchanged unless the change is a deliberate, documented correction.
   A change that alters any daily label or any table value must say so in `CHANGELOG.md` and explain why.
3. Add a known-answer test for every new function or option: build an input whose correct output
   is known exactly (for example a synthetic day with a planted azimuth) and check that it is recovered.
4. Run the whole test suite on your machine before you submit the change.
5. Keep the code style of the package: plain functions, NumPy-style docstrings, type hints on public
   functions, and clear error messages that tell the user what to change.
6. Describe the change in `CHANGELOG.md` under a new "Unreleased" heading.

## Releases

Versions follow Semantic Versioning. The version number appears in `pyproject.toml`,
`imf_polarity/__init__.py` and `CITATION.cff`, and the three must agree.
