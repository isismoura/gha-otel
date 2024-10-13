# GitHub Workflow Tracing with OpenTelemetry

This project integrates OpenTelemetry tracing with GitHub workflow runs, jobs, and steps, exporting traces to Honeycomb for analysis. It allows tracing of GitHub workflows by creating spans for workflow runs, jobs, and steps, capturing metadata and timing information.

## Features

- **OpenTelemetry Integration**: Traces GitHub workflows, jobs, and steps, exporting spans via the OTLP exporter.
- **GitHub API Integration**: Fetches workflow runs, jobs, and steps using the GitHub API.
- **Honeycomb Exporter**: Exports trace data to Honeycomb for observability and monitoring.
- **Customizable Execution**: Allows filtering workflows by repository, organization, and time range.

## Setup

### Prerequisites

- Python 3.x
- GitHub Personal Access Token
- Honeycomb API Key
- `.env` file with the following variables:
  - `GITHUB_AUTH_TOKEN`: Your GitHub token.
  - `HC_TEAM_TOKEN`: Your Honeycomb team token.

### Installation

1. Clone the repository:

    ```console
    git clone <repository-url>
    cd <repository-directory>

2. Install the required dependencies:

    ```console
    pip install -r requirements.txt

3. Set up environment variables in a .env file:
    `GITHUB_AUTH_TOKEN=<your-github-token>`
    `HC_TEAM_TOKEN=<your-honeycomb-token>`
    

### Usage

1. Run the script with the required arguments:

    ```console
    python script.py --repo <repository-name> --workflow <workflow-name> [--org <organization>] [--start <timestamp>] [--end <timestamp>]

Example:

    python script.py --repo my-repo --workflow CI --org my-org --start 2023-08-01 --end 2023-09-01


## Arguments

- `--org`: (Optional) GitHub organization name. If not provided, defaults to the authenticated user's login.
- `--repo`: (Required) GitHub repository name.
- `--workflow`: (Required) GitHub workflow name.
- `--start`: (Optional) Start timestamp in `YYYY-MM-DD` format.
- `--end`: (Optional) End timestamp in `YYYY-MM-DD` format.
- `--skipsteps`: (Optional) Skip steps if this flag is provided.

## Tracing Details

The script uses OpenTelemetry to trace the following GitHub workflow elements:

- **Workflow Runs**: A span is created for each run, capturing metadata such as run ID, run attempt, status, and timestamps.
- **Jobs**: A child span is created for each job within a workflow run, capturing job details like runner information and status.
- **Steps**: A child span of the job is created for each step in a job, capturing step number, name, and timing information.

## Exporting Traces

- **Honeycomb**: Traces are exported to Honeycomb via OTLP. Ensure that the `HC_TEAM_TOKEN` is set in your environment to authenticate the exporter.

