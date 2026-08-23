"""`shuddhi doctor` exists for one failure: the Python that runs the command
is not the Python the dependencies were installed into."""

from shuddhi import cli as factory

def test_doctor_flags_a_venv_that_is_not_the_running_interpreter(monkeypatch, capsys):
    """Sid's first real run: prompt said (.venv), doctor said anaconda, and
    every extra he had just installed showed 'absent'. doctor reported the
    truth but not the contradiction. An activated venv that is not the
    interpreter running the command is THE failure this command exists for,
    so it must be named and must fail readiness."""
    monkeypatch.setenv("VIRTUAL_ENV", "/definitely/not/this/interpreter")
    monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)
    rc = factory.main(["doctor"])
    out = capsys.readouterr().out
    assert "MISMATCH" in out
    assert "/definitely/not/this/interpreter/bin/shuddhi doctor" in out
    assert rc != 0


def test_doctor_describes_the_running_interpreter_not_the_shell(monkeypatch, capsys):
    """Sid's second run: the interpreter line said .venv/bin/python3, the
    environment line said 'conda env: base'. Both variables were set in his
    shell; doctor believed the shell over the interpreter. The environment
    reported must be the one sys.prefix actually lives in."""
    import sys
    monkeypatch.setenv("VIRTUAL_ENV", sys.prefix)
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "base")
    monkeypatch.setenv("CONDA_PREFIX", "/somewhere/conda/that/is/not/sys.prefix")
    factory.main(["doctor"])
    out = capsys.readouterr().out
    assert "environment venv:" in out
    assert "conda env: base" not in out
