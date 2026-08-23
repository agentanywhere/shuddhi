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
