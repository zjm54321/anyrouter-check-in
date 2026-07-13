import io
from contextlib import redirect_stdout

import pytest

import proof_harness.models as progress
from proof_harness.models import ProgressStage


class RecordingOutput:
	def __init__(self) -> None:
		self.parts: list[str] = []
		self.flushes: int = 0

	def write(self, value: str) -> int:
		self.parts.append(value)
		return len(value)

	def flush(self) -> None:
		self.flushes += 1


def test_progress_record_is_fixed_redirect_safe_and_immediately_flushed(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# Given
	output = RecordingOutput()
	monkeypatch.setattr(progress, '_PROGRESS_OUTPUT', output)

	# When
	with redirect_stdout(io.StringIO()):
		progress.emit_progress(True, ProgressStage.LOGIN_NAVIGATION)

	# Then
	assert ''.join(output.parts) == '{"event":"proof_progress","stage":"login_navigation"}\n'
	assert output.flushes == 1


def test_disabled_progress_writes_and_flushes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
	# Given
	output = RecordingOutput()
	monkeypatch.setattr(progress, '_PROGRESS_OUTPUT', output)

	# When
	progress.emit_progress(False, ProgressStage.COMPLETE)

	# Then
	assert output.parts == []
	assert output.flushes == 0


def test_progress_stages_are_a_closed_fixed_set() -> None:
	# Given / When
	stages = {stage.value for stage in ProgressStage}

	# Then
	assert stages == {
		'browser_launch',
		'login_navigation',
		'form_submission',
		'login_verification',
		'browser_egress',
		'browser_close_start',
		'browser_close_end',
		'http_egress',
		'pre_read',
		'sign_in',
		'post_read',
		'complete',
	}
