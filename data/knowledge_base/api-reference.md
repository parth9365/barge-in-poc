# NovaBoard - API Reference

## Overview

The NovaBoard REST API allows you to programmatically manage projects, tasks, sprints, and users. The API follows RESTful conventions and returns JSON responses.

**Base URL**: `https://api.novaboard.example.com/v2`

The API is available on Pro and Enterprise plans. Free plan users do not have API access.

## Authentication

All API requests require authentication using an API key or OAuth 2.0 token.

### API Key Authentication

Generate an API key from **Settings > API > Generate Key** in NovaBoard.

Include the key in the `Authorization` header:
```
Authorization: Bearer nb_live_abc123xyz
```

API keys have the same permissions as the user who created them. Keys can be scoped to read-only or read-write access.

### OAuth 2.0

For applications that act on behalf of users, use OAuth 2.0 with the Authorization Code flow.

- **Authorization URL**: `https://auth.novaboard.example.com/oauth/authorize`
- **Token URL**: `https://auth.novaboard.example.com/oauth/token`
- **Scopes**: `read`, `write`, `admin`

Access tokens expire after 1 hour. Use the refresh token to obtain a new access token.

## Rate Limits

- **Pro Plan**: 1,000 requests per hour per API key
- **Enterprise Plan**: 10,000 requests per hour per API key

Rate limit headers are included in every response:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 847
X-RateLimit-Reset: 1709251200
```

When rate limited, the API returns HTTP 429 with a `Retry-After` header.

## Core Endpoints

### Projects

#### List Projects
```
GET /projects
```
Returns all projects the authenticated user has access to.

Query parameters:
- `status` (string): Filter by status. Values: `active`, `archived`, `all`. Default: `active`.
- `page` (integer): Page number. Default: 1.
- `per_page` (integer): Items per page. Default: 20, max: 100.

#### Get Project
```
GET /projects/{project_id}
```
Returns a single project with its settings and metadata.

#### Create Project
```
POST /projects
```
Request body:
```json
{
  "name": "My Project",
  "description": "Project description",
  "methodology": "scrum",
  "default_view": "kanban"
}
```

#### Update Project
```
PATCH /projects/{project_id}
```

#### Delete Project
```
DELETE /projects/{project_id}
```
Soft-deletes the project. Data is retained for 30 days.

### Tasks

#### List Tasks
```
GET /projects/{project_id}/tasks
```
Query parameters:
- `status` (string): `open`, `in_progress`, `in_review`, `done`, `all`
- `assignee` (string): User ID to filter by assignee
- `priority` (string): `critical`, `high`, `medium`, `low`
- `sprint_id` (string): Filter by sprint
- `label` (string): Filter by label (comma-separated for multiple)
- `search` (string): Full-text search in title and description
- `sort` (string): `created_at`, `updated_at`, `priority`, `due_date`. Default: `created_at`
- `order` (string): `asc` or `desc`. Default: `desc`

#### Get Task
```
GET /projects/{project_id}/tasks/{task_id}
```
Returns the task with all fields, comments, attachments, and activity log.

#### Create Task
```
POST /projects/{project_id}/tasks
```
Request body:
```json
{
  "title": "Implement user authentication",
  "description": "Add OAuth 2.0 login flow",
  "assignee_id": "user_abc123",
  "priority": "high",
  "labels": ["backend", "security"],
  "due_date": "2025-04-15",
  "sprint_id": "sprint_xyz",
  "custom_fields": {
    "story_points": 5,
    "component": "auth-service"
  }
}
```

#### Update Task
```
PATCH /projects/{project_id}/tasks/{task_id}
```

#### Delete Task
```
DELETE /projects/{project_id}/tasks/{task_id}
```

#### Add Comment
```
POST /projects/{project_id}/tasks/{task_id}/comments
```
Request body:
```json
{
  "body": "This looks good. Merging now.",
  "mentions": ["user_def456"]
}
```

### Sprints

#### List Sprints
```
GET /projects/{project_id}/sprints
```
Query parameters:
- `status` (string): `planning`, `active`, `completed`, `all`

#### Get Sprint
```
GET /projects/{project_id}/sprints/{sprint_id}
```
Returns sprint details including velocity, burndown data, and task breakdown.

#### Create Sprint
```
POST /projects/{project_id}/sprints
```
Request body:
```json
{
  "name": "Sprint 42",
  "start_date": "2025-04-01",
  "end_date": "2025-04-14",
  "goal": "Complete authentication module"
}
```

#### Start Sprint
```
POST /projects/{project_id}/sprints/{sprint_id}/start
```

#### Complete Sprint
```
POST /projects/{project_id}/sprints/{sprint_id}/complete
```
Moves incomplete tasks to the backlog or next sprint.

### Users

#### List Team Members
```
GET /projects/{project_id}/members
```

#### Get Current User
```
GET /me
```

#### Update User Profile
```
PATCH /me
```

## Webhooks

NovaBoard can send HTTP POST notifications to your server when events occur.

### Configuring Webhooks

Set up webhooks in **Settings > Integrations > Webhooks** or via the API:

```
POST /webhooks
```
Request body:
```json
{
  "url": "https://your-server.example.com/novaboard-webhook",
  "events": ["task.created", "task.updated", "sprint.completed"],
  "secret": "your_webhook_secret"
}
```

### Available Events

- `task.created`, `task.updated`, `task.deleted`, `task.commented`
- `sprint.created`, `sprint.started`, `sprint.completed`
- `project.created`, `project.archived`
- `member.added`, `member.removed`
- `automation.triggered`, `automation.failed`

### Webhook Payload

All webhook payloads follow this format:
```json
{
  "event": "task.updated",
  "timestamp": "2025-04-01T12:00:00Z",
  "data": {
    "task_id": "task_abc123",
    "project_id": "proj_xyz789",
    "changes": {
      "status": {"from": "open", "to": "in_progress"},
      "assignee_id": {"from": null, "to": "user_def456"}
    }
  }
}
```

### Webhook Security

Webhooks include an `X-Nova-Signature` header containing an HMAC-SHA256 signature of the payload using your webhook secret. Always verify this signature before processing the webhook.

## Error Handling

The API uses standard HTTP status codes:

- `200 OK`: Request succeeded
- `201 Created`: Resource created
- `204 No Content`: Resource deleted
- `400 Bad Request`: Invalid request body or parameters
- `401 Unauthorized`: Missing or invalid authentication
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Resource does not exist
- `409 Conflict`: Resource conflict (e.g., duplicate name)
- `422 Unprocessable Entity`: Validation error
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server-side error (contact support)

Error response format:
```json
{
  "error": {
    "code": "validation_error",
    "message": "Task title is required",
    "details": [
      {"field": "title", "message": "This field is required"}
    ]
  }
}
```

## SDKs and Libraries

Official client libraries:
- **Python**: `pip install novaboard` (supports async with `novaboard[async]`)
- **JavaScript/TypeScript**: `npm install @novatech/novaboard`
- **Go**: `go get github.com/novatech/novaboard-go`
- **Ruby**: `gem install novaboard`

Community-maintained:
- **Java**: `novaboard-java` (Maven Central)
- **C#**: `NovaTech.NovaBoard` (NuGet)
