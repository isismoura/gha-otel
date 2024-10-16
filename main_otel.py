from opentelemetry import trace
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from github import (
    Github,
    Auth,
    GithubException,
    PaginatedList,
    WorkflowRun,
    Workflow,
    Repository,
    WorkflowJob,
)
import argparse
import sys
import os
from datetime import datetime
from dotenv import load_dotenv
import uuid
import json

load_dotenv()


resource = Resource.create(
    {"service.name": "my-service"}
)  # Create a resource to describe this service

team_key = os.getenv("HC_TEAM_TOKEN")

if team_key is None:
    print("🔴 Environment Variable HC_TEAM_TOKEN is missing")
    sys.exit()


# Configure the OTLP exporter to use HTTP/protobuf and export to the external URL
otlp_exporter = OTLPSpanExporter(
    endpoint="https://api.honeycomb.io:443/v1/traces",  # Replace with your external URL
    headers={
        "x-honeycomb-team": team_key,  # Replace with necessary headers if required
    },
)

provider = TracerProvider(resource=resource)
processor = BatchSpanProcessor(otlp_exporter)
processor_console = BatchSpanProcessor(ConsoleSpanExporter())

provider.add_span_processor(processor)
# provider.add_span_processor(processor_console)

trace.set_tracer_provider(provider)  # Sets the global default tracer provider
tracer = trace.get_tracer(
    "my.tracer.name"
)  # Creates a tracer from the global tracer provider

key = os.getenv("GITHUB_AUTH_TOKEN")

if key is None:
    print("🔴 Environment Variable GITHUB_AUTH_TOKEN is missing")
    sys.exit()

auth = Auth.Token(key)
g = Github(auth=auth)

execution_id = str(uuid.uuid4())
print(f"\n👉 Execution ID: {execution_id}")


def main(**kwargs):

    org, repo_name, workflow_name, start, end, skip = get_args(**kwargs)
    print(
        f"👉 Org/User: {org}, Repo: {repo_name}, Workflow: {workflow_name}, Start: {start}, End: {end}, Skip Steps: {skip}\n"
    )
    repo = get_repo(org, repo_name)

    workflow = get_workflow(workflow_name, repo)

    runs, run_spans = process_runs(workflow, start, end)

    jobs, job_spans = process_jobs(runs, run_spans, repo)

    if skip == False:
        steps = process_steps(jobs, job_spans)

    print("✅ All done!")


def get_args(**kwargs):
    # Get required arguments
    repo_name = kwargs.get("repo")
    workflow_name = kwargs.get("workflow")

    # Check if required arguments are missing
    if repo_name is None or workflow_name is None:
        print("🔴 Missing required arguments (repo) and/or (workflow)")
        sys.exit()

    # Get optional arguments: org and timestamp (start and end)
    org = kwargs.get("org")
    if org is None:
        user = g.get_user()
        org = user.login  # If org is not provided, the default is the user's username

    # Get start and end timestamps
    start = kwargs.get("start")
    end = kwargs.get("end")

    # Handle the case where one of the timestamps is missing
    if (start is None and end is not None) or (start is not None and end is None):
        print("🔴 Missing start or end timestamp")
        sys.exit()

    # Check if skip steps was provided
    if kwargs.get("skipsteps"):
        skip = True
    else:
        skip = False

    return org, repo_name, workflow_name, start, end, skip


def get_repo(org: str, repo_name: str) -> Repository.Repository:
    print(f"⏳ Fetching repository '{org}/{repo_name}'...")
    try:
        repo = g.get_repo(f"{org}/{repo_name}")
        print(f"🟢 Repository '{repo.name}' found!\n")
        return repo
    except GithubException:
        print(f"🔴 Repository '{org}/{repo_name}' not found.")
        sys.exit()


def get_workflow(workflow_name: str, repo: Repository.Repository):
    print(f"⏳ Searching for workflow '{workflow_name}'...")
    workflows = repo.get_workflows()
    workflow = None
    for wf in workflows:
        if wf.name == workflow_name:
            workflow = wf
            print(f"🟢 Workflow '{workflow.name}' found!\n")
            return workflow
    if workflow is None:
        print(f"🔴 Workflow '{workflow_name}' not found")
        sys.exit()


def process_runs(workflow: Workflow.Workflow, start: str | None, end: str | None):
    print(f"⏳ Fetching workflow runs for '{workflow.name}'...")
    if start is None and end is None:
        runs = workflow.get_runs()
    else:
        print(f"⏳ Filtering runs between {start} and {end}.")
        runs = workflow.get_runs(created=f"{start}..{end}")

    run_spans = []

    for run in runs:
        run_start_time = convert_time(run.run_started_at)
        if run.status == "completed":
            run_completed_at = convert_time(run.updated_at)
        else:
            run_completed_at = None
        run_name = run.path.split("/")[-1].split(".")[0]

        # Start the span manually for the run
        run_span_context_manager = tracer.start_as_current_span(
            run_name, start_time=run_start_time, end_on_exit=False
        )
        parent_span = (
            run_span_context_manager.__enter__()
        )  # Manually enter the context to get the span object

        today = str(datetime.today())

        parent_span.set_attribute("execution.id", execution_id)
        parent_span.set_attribute("workflow.id", workflow.id)
        parent_span.set_attribute("run.id", run.id)
        parent_span.set_attribute("run.run_number", run.run_number)
        if run.run_attempt is None:
            parent_span.set_attribute("run.run_attempt", 1)
        else:
            parent_span.set_attribute("run.run_attempt", run.run_attempt)
        parent_span.set_attribute("run.html_url", run.html_url)
        parent_span.set_attribute("run.event", run.event)
        parent_span.set_attribute("run.name", run.name)
        parent_span.set_attribute("run.run_started_at", run_start_time)
        parent_span.set_attribute("run.updated_at", run_completed_at)
        parent_span.set_attribute("my_date", today)
        parent_span.set_attribute("run.conclusion", run.conclusion)

        if run.conclusion == "failure":
            parent_span.set_status(StatusCode.ERROR, f"Run {run.run_number} failed")
            parent_span.set_attribute("error", True)
            parent_span.set_attribute("error.message", f"Run {run.run_number} failed")

        run_spans.append(parent_span)

        if run_completed_at:
            parent_span.end(end_time=run_completed_at)
            run_span_context_manager.__exit__(None, None, None)

    print(f"🟢 {len(run_spans)} run(s) processed!\n")

    return runs, run_spans


def process_jobs(
    runs: PaginatedList.PaginatedList[WorkflowRun.WorkflowRun],
    run_spans: list,
    repo: Repository.Repository,
):
    print("⏳ Processing jobs...")
    all_jobs = []
    job_spans = []

    for run, parent_span in zip(runs, run_spans):
        jobs = run.jobs()
        for job in jobs:

            job_started_at = convert_time(job.started_at)
            job_completed_at = convert_time(job.completed_at)
            job_created_at = convert_time(job.created_at)
            queue_time = (job_started_at - job_created_at)/1000000000

            # Start the span manually for the job
            job_span_context_manager = tracer.start_as_current_span(
                job.name,
                start_time=job_started_at,
                context=trace.set_span_in_context(parent_span),
                end_on_exit=False,
            )
            child_span = (
                job_span_context_manager.__enter__()
            )  # Manually enter the context to get the span object

            if job.labels is None:
                job_labels = []
            else:
                if isinstance(job.labels, (list, tuple)):
                    job_labels = job.labels
                else:
                    job_labels = [job.labels]
            child_span.set_attribute("runs_on", "".join(job_labels))
            child_span.set_attribute("execution.id", execution_id)
            child_span.set_attribute("job.id", job.id)
            child_span.set_attribute("job.run_id", job.run_id)
            if job.run_attempt is None:
                child_span.set_attribute("job.run_attempt", 1)
            else:
                child_span.set_attribute("job.run_attempt", job.run_attempt)
            if job.runner_group_id is not None:
                child_span.set_attribute("job.runner_group_id", job.runner_group_id)
            if job.runner_group_id is not None:
                child_span.set_attribute("job.runner_group_name", job.runner_group_name)
            if job.runner_name is not None:
                child_span.set_attribute("job.runner_name", job.runner_name)
            child_span.set_attribute("job.started_at", job_started_at)
            child_span.set_attribute("job.completed_at", job_completed_at)
            child_span.set_attribute("job.created_at", job_created_at)
            child_span.set_attribute("job.queue_time_seconds", queue_time)

            annotations, error = fetch_annotations(repo, job.id)
            if error:
                print(f"🔴 Failed to fetch annotations for job {job.id}: {error}")
            else:
                for item in annotations:
                    child_span.add_event(
                        job.conclusion,
                        attributes={
                            "message": item.message,
                            "annotation_level": item.annotation_level,
                            "title": item.title,
                        },
                        timestamp=job_started_at,
                    )

            if job.conclusion == "failure":
                child_span.set_status(StatusCode.ERROR, f"Job {job.name} failed")
                child_span.set_attribute("error", True)
                child_span.set_attribute("error.message", f"Job {job.name} failed")

            # End the job span with the correct completed time
            child_span.end(end_time=job_completed_at)
            job_span_context_manager.__exit__(None, None, None)

            all_jobs.append(job)
            job_spans.append(child_span)

    print(f"🟢 {len(all_jobs)} job(s) processed!\n")

    return all_jobs, job_spans


def process_steps(jobs: list[WorkflowJob.WorkflowJob], job_spans: list):
    print("⏳ Processing steps...")
    all_steps = []
    for job, parent_span in zip(jobs, job_spans):
        steps = job.steps
        for step in steps:
            step_started_at = convert_time(step.started_at)
            step_completed_at = convert_time(step.completed_at)

            # Start the span manually
            span_context_manager = tracer.start_as_current_span(
                step.name,
                start_time=step_started_at,
                context=trace.set_span_in_context(parent_span),
                end_on_exit=False,
            )
            grandchild_span = (
                span_context_manager.__enter__()
            )  # Manually enter the context to get the span object

            grandchild_span.set_attribute("execution.id", execution_id)
            grandchild_span.set_attribute("step.name", step.name)
            grandchild_span.set_attribute("step.number", step.number)
            grandchild_span.set_attribute("step.started_at", step_started_at)
            grandchild_span.set_attribute("step.completed_at", step_completed_at)

            if step.conclusion == "failure":
                grandchild_span.set_status(StatusCode.ERROR, f"Step {step.name} failed")
                grandchild_span.set_attribute("error", True)
                grandchild_span.set_attribute(
                    "error.message", f"Step {step.name} failed"
                )

            # End the span with the correct completed time
            grandchild_span.end(end_time=step_completed_at)
            span_context_manager.__exit__(None, None, None)

            all_steps.append(step)

    print(f"🟢 {len(all_steps)} step(s) processed!\n")

    return all_steps


def convert_time(time):
    return int(time.timestamp() * 1e9)


def fetch_annotations(repo: Repository.Repository, job_id):
    try:
        check_run = repo.get_check_run(job_id)
        annotations = check_run.get_annotations()
        return annotations, None
    except Exception as e:
        return [], str(e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process data")
    parser.add_argument("--org", type=str, help="Organization name (optional)")
    parser.add_argument("--repo", type=str, required=True, help="Repository (required)")
    parser.add_argument(
        "--workflow", type=str, required=True, help="Workflow name (required)"
    )
    parser.add_argument("--start", type=str, help="Start Date YYYY-MM-DD (optional)")
    parser.add_argument("--end", type=str, help="End Date YYYY-MM-DD (optional)")
    parser.add_argument(
        "--skipsteps", action="store_true", help="Skip steps if this flag is provided"
    )
    args = vars(parser.parse_args())
    main(**args)


g.close()
