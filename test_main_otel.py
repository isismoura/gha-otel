import pytest
from unittest import mock
from datetime import datetime
from github import GithubException
from opentelemetry.trace import Span, SpanContext
from main_otel import (
    main,
    get_args,
    get_repo,
    get_workflow,
    process_runs,
    process_jobs,
    process_steps,
    fetch_annotations,
    convert_time,
)


# Mocked environment variables and setup
@pytest.fixture
def mock_env_vars(monkeypatch):
    monkeypatch.setenv("HC_TEAM_TOKEN", "test_team_token")
    monkeypatch.setenv("GITHUB_AUTH_TOKEN", "test_github_token")


@pytest.fixture
def mock_github_repo():
    # Mock repository with a dummy name
    mock_repo = mock.Mock()
    mock_repo.name = "test-repo"
    return mock_repo


@pytest.fixture
def mock_workflow():
    # Mock workflow with a dummy name
    mock_workflow = mock.Mock()
    mock_workflow.name = "test-workflow"
    return mock_workflow


# Test get_args function
def test_get_args():
    kwargs = {
        "repo": "test-repo",
        "workflow": "test-workflow",
        "org": "test-org",
        "start": None,
        "end": None,
        "skipsteps": True,
    }
    org, repo_name, workflow_name, start, end, skip = get_args(**kwargs)
    assert org == "test-org"
    assert repo_name == "test-repo"
    assert workflow_name == "test-workflow"
    assert start is None
    assert end is None
    assert skip is True


# Test get_repo function when the repository is found
def test_get_repo(mock_github_repo):
    with mock.patch("main_otel.g.get_repo", return_value=mock_github_repo):
        repo = get_repo("test-org", "test-repo")
        assert repo.name == "test-repo"


# Test get_repo function when the repository is not found
def test_get_repo_not_found():
    with mock.patch(
        "main_otel.g.get_repo", side_effect=GithubException(404, "Not Found")
    ):
        with pytest.raises(SystemExit):
            get_repo("test-org", "nonexistent-repo")


# Test get_workflow function when the workflow is found
def test_get_workflow(mock_github_repo, mock_workflow):
    mock_github_repo.get_workflows.return_value = [mock_workflow]
    workflow = get_workflow("test-workflow", mock_github_repo)
    assert workflow.name == "test-workflow"


# Test get_workflow function when the workflow is not found
def test_get_workflow_not_found(mock_github_repo):
    mock_github_repo.get_workflows.return_value = []
    with pytest.raises(SystemExit):
        get_workflow("nonexistent-workflow", mock_github_repo)


# Mock processing runs
def test_process_runs(mock_workflow):
    # Create a mock for the workflow run
    mock_run = mock.Mock()
    mock_run.run_started_at = datetime(2024, 1, 1, 12, 0, 0)
    mock_run.updated_at = datetime(2024, 1, 1, 12, 30, 0)
    mock_run.status = "completed"
    mock_run.path = "some/workflow/run/path/file.ext"  # Add the path attribute
    mock_run.id = 1
    mock_run.run_number = 42
    mock_run.run_attempt = 1
    mock_run.html_url = "http://example.com"
    mock_run.event = "push"
    mock_run.name = "mock-run"
    mock_run.conclusion = "success"

    # Mock the workflow.get_runs method
    mock_workflow.get_runs.return_value = [mock_run]

    # Call process_runs
    runs, run_spans = process_runs(mock_workflow, None, None)

    # Assertions
    assert len(runs) == 1
    assert len(run_spans) == 1


# Test process_jobs
def test_process_jobs(mock_github_repo, mock_workflow):
    mock_job = mock.Mock()
    mock_job.started_at = datetime(2024, 1, 1, 12, 0, 0)
    mock_job.completed_at = datetime(2024, 1, 1, 12, 30, 0)
    mock_job.labels = ["label1", "label2"]

    mock_annotations = [
        mock.Mock(
            message="Sample message", annotation_level="warning", title="Sample title"
        )
    ]
    mock_fetch_annotations = mock.Mock(return_value=(mock_annotations, None))

    mock_run = mock.Mock(jobs=mock.Mock(return_value=[mock_job]))

    mock_span = mock.Mock()
    mock_span.get_span_context.return_value = mock.Mock(
        trace_id=12345678901234567890, span_id=9876543210123456, is_remote=False
    )

    with mock.patch("main_otel.fetch_annotations", mock_fetch_annotations):
        jobs, job_spans = process_jobs(
            [mock_run], [mock_span], "test-org", mock_github_repo
        )

    assert len(jobs) == len(job_spans) == 1


# Test process_steps
def test_process_steps():
    mock_job = mock.Mock()
    mock_step = mock.Mock()
    mock_step.name = "Sample Step"  # Set the step name
    mock_step.started_at = datetime(2024, 1, 1, 12, 0, 0)
    mock_step.completed_at = datetime(2024, 1, 1, 12, 30, 0)
    mock_step.conclusion = "success"  # Set a valid conclusion
    mock_job.steps = [mock_step]

    jobs = [mock_job]

    # Create a valid Span mock with a proper span context
    mock_span_context = mock.Mock(spec=SpanContext)
    mock_span_context.trace_id = 12345678901234567890
    mock_span_context.span_id = 9876543210123456
    mock_span_context.is_remote = False

    mock_span = mock.Mock(spec=Span)
    mock_span.get_span_context.return_value = mock_span_context

    job_spans = [mock_span]

    steps = process_steps(jobs, job_spans)

    assert len(steps) == 1


# Test convert_time function
def test_convert_time():
    time = datetime(2024, 1, 1, 12, 0, 0)
    timestamp = convert_time(time)
    assert timestamp == int(time.timestamp() * 1e9)


# Test fetch_annotations with no exception
def test_fetch_annotations(mock_github_repo):
    mock_check_run = mock.Mock()
    mock_check_run.get_annotations.return_value = ["test_annotation"]
    mock_github_repo.get_check_run.return_value = mock_check_run

    annotations, error = fetch_annotations(mock_github_repo, 1)
    assert annotations == ["test_annotation"]
    assert error is None


# Test fetch_annotations with exception
def test_fetch_annotations_exception(mock_github_repo):
    mock_github_repo.get_check_run.side_effect = Exception("Test error")
    annotations, error = fetch_annotations(mock_github_repo, 1)
    assert annotations == []
    assert error == "Test error"
