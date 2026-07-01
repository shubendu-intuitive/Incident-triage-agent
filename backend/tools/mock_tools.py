"""
tools/mock_tools.py

14 mock tools that simulate AWS service calls.

"""

import os
from langchain_core.tools import tool

# We'll pass the scenario in at call time via a module-level variable.
# In a real system this would come from a context var or dependency injection.
_current_scenario = "auto_fix"


def set_scenario(scenario: str):
    global _current_scenario
    _current_scenario = scenario


def get_scenario() -> str:
    return _current_scenario


# ── Investigation Tools (always run in parallel at graph start) ───────────────

@tool
def fetch_recent_logs(service: str, time_window_minutes: int = 30) -> dict:
    """Fetch recent error logs for a service from CloudWatch Logs."""
    scenario = get_scenario()

    if scenario == "auto_fix":
        return {
            "service": service,
            "time_window_minutes": time_window_minutes,
            "error_count": 147,
            "top_errors": [
                {"message": "Runtime.ExitError: Process exited before completing request", "count": 89},
                {"message": "FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory", "count": 41},
                {"message": "Task timed out after 30.00 seconds", "count": 17},
            ],
            "pattern": "MemoryError",
            "sample_log": "[ERROR] 2024-01-15T10:23:41Z kb-ingestion-lambda FATAL ERROR: heap out of memory",
        }

    elif scenario == "external_dependency":
        return {
            "service": service,
            "time_window_minutes": time_window_minutes,
            "error_count": 12,
            "top_errors": [
                {"message": "RequestTimeout: Request to bedrock-runtime timed out after 29000ms", "count": 9},
                {"message": "ThrottlingException: Rate exceeded for Bedrock", "count": 3},
            ],
            "pattern": "DependencyTimeout",
            "sample_log": "[WARN] 2024-01-15T10:23:41Z amp-api-gateway RequestTimeout: bedrock-runtime 29000ms",
        }

    elif scenario == "cascading_failure":
        return {
            "service": service,
            "time_window_minutes": time_window_minutes,
            "error_count": 2341,
            "top_errors": [
                {"message": "ProvisionedThroughputExceededException: The level of configured provisioned throughput for the table was exceeded", "count": 1876},
                {"message": "Internal Server Error: DynamoDB write failed after 3 retries", "count": 412},
                {"message": "SQS consumer failed to process message, requeuing", "count": 53},
            ],
            "pattern": "DynamoDBThrottling",
            "sample_log": "[ERROR] 2024-01-15T10:23:41Z workspace-api ProvisionedThroughputExceededException",
        }

    return {"error": "Unknown scenario", "error_count": 0}


@tool
def get_error_metrics(service: str) -> dict:
    """Get current error rate and latency metrics from CloudWatch Metrics."""
    scenario = get_scenario()

    if scenario == "auto_fix":
        return {
            "service": service,
            "error_rate_pct": 8.3,
            "latency_p99_ms": 28500,   # Lambda timeout is 30s
            "latency_p50_ms": 4200,
            "request_volume": 340,
            "spike_started_at": "2024-01-15T10:18:00Z",
            "trend": "increasing",
        }

    elif scenario == "external_dependency":
        return {
            "service": service,
            "error_rate_pct": 2.1,      # Low error rate but very high latency
            "latency_p99_ms": 31000,
            "latency_p50_ms": 2800,
            "request_volume": 1240,
            "spike_started_at": "2024-01-15T10:05:00Z",
            "trend": "stable_high",     # Not getting worse, but already bad
        }

    elif scenario == "cascading_failure":
        return {
            "service": service,
            "error_rate_pct": 23.4,
            "latency_p99_ms": 8900,
            "latency_p50_ms": 3100,
            "request_volume": 2100,
            "spike_started_at": "2024-01-15T10:20:00Z",
            "trend": "rapidly_increasing",
        }

    return {}


@tool
def check_queue_depth(queue_name: str) -> dict:
    """Check SQS queue depth and consumer lag."""
    scenario = get_scenario()

    if scenario == "auto_fix":
        return {
            "queue_name": queue_name,
            "depth": 1240,
            "consumer_lag": "18 minutes",
            "trend": "increasing",
            "messages_in_flight": 32,
            "oldest_message_age_sec": 1080,
        }

    elif scenario == "external_dependency":
        return {
            "queue_name": queue_name,
            "depth": 45,
            "consumer_lag": "2 minutes",
            "trend": "stable",
            "messages_in_flight": 8,
            "oldest_message_age_sec": 120,
        }

    elif scenario == "cascading_failure":
        return {
            "queue_name": queue_name,
            "depth": 8412,             # Retry storm — queue backing up fast
            "consumer_lag": "94 minutes",
            "trend": "rapidly_increasing",
            "messages_in_flight": 1200,
            "oldest_message_age_sec": 5640,
            "dlq_depth": 234,          # Dead letter queue also filling up
        }

    return {}


# ── Deep Diagnosis Tools (called if initial investigation is ambiguous) ────────

@tool
def get_dependency_health(service: str) -> dict:
    """Check health of downstream service dependencies."""
    scenario = get_scenario()

    if scenario == "auto_fix":
        return {
            "service": service,
            "dependencies": [
                {"name": "dynamodb", "status": "healthy", "response_time_ms": 12, "normal_ms": 10},
                {"name": "s3", "status": "healthy", "response_time_ms": 45, "normal_ms": 40},
            ],
        }

    elif scenario == "external_dependency":
        return {
            "service": service,
            "dependencies": [
                {"name": "bedrock-runtime", "status": "degraded", "response_time_ms": 28500, "normal_ms": 800},
                {"name": "dynamodb", "status": "healthy", "response_time_ms": 11, "normal_ms": 10},
                {"name": "cognito", "status": "healthy", "response_time_ms": 89, "normal_ms": 85},
            ],
        }

    elif scenario == "cascading_failure":
        return {
            "service": service,
            "dependencies": [
                {"name": "dynamodb-workspace-table", "status": "degraded", "response_time_ms": 5200, "normal_ms": 15},
                {"name": "elasticache", "status": "healthy", "response_time_ms": 2, "normal_ms": 2},
                {"name": "s3", "status": "healthy", "response_time_ms": 48, "normal_ms": 40},
            ],
        }

    return {}


@tool
def check_recent_deployments(service: str) -> dict:
    """Check recent deployments for a service in the last 24 hours."""
    scenario = get_scenario()

    if scenario == "auto_fix":
        return {
            "service": service,
            "deployments": [
                {
                    "version": "v2.4.1",
                    "deployed_at": "2024-01-15T09:45:00Z",  # 30 min before incident
                    "deployed_by": "github-actions",
                    "status": "successful",
                    "change_summary": "Updated document parser, increased batch size from 10 to 50",
                }
            ],
        }

    elif scenario == "external_dependency":
        return {
            "service": service,
            "deployments": [],   # No recent deployments — rules out code change as cause
        }

    elif scenario == "cascading_failure":
        return {
            "service": service,
            "deployments": [
                {
                    "version": "v1.8.3",
                    "deployed_at": "2024-01-14T14:00:00Z",  # Yesterday — unlikely cause
                    "deployed_by": "terraform",
                    "status": "successful",
                    "change_summary": "Infrastructure update, no application changes",
                }
            ],
        }

    return {}


@tool
def check_aws_service_health(aws_service: str) -> dict:
    """Check AWS service health dashboard for a given service name."""
    scenario = get_scenario()

    if scenario == "external_dependency" and "bedrock" in aws_service.lower():
        return {
            "aws_service": aws_service,
            "status": "service_disruption",
            "message": "We are investigating increased error rates and latencies for Amazon Bedrock in the US-EAST-1 region.",
            "affected_regions": ["us-east-1"],
            "started_at": "2024-01-15T09:58:00Z",
            "severity": "high",
        }

    return {
        "aws_service": aws_service,
        "status": "service_is_operating_normally",
        "message": "No issues currently.",
        "affected_regions": [],
    }


@tool
def get_dynamodb_metrics(table_name: str) -> dict:
    """Get DynamoDB table capacity utilisation and throttling metrics."""
    scenario = get_scenario()

    if scenario == "cascading_failure":
        return {
            "table_name": table_name,
            "read_capacity_pct": 34.2,
            "write_capacity_pct": 99.1, 
            "throttled_requests": 1876,
            "provisioned_read_units": 100,
            "provisioned_write_units": 200,
            "consumed_write_units_avg": 198.2,
        }

    return {
        "table_name": table_name,
        "read_capacity_pct": 22.0,
        "write_capacity_pct": 18.5,
        "throttled_requests": 0,
        "provisioned_read_units": 100,
        "provisioned_write_units": 200,
    }


@tool
def fetch_runbook(error_pattern: str) -> dict:
    """Fetch the relevant runbook for a given error pattern."""
    scenario = get_scenario()

    if scenario == "auto_fix":
        return {
            "found": True,
            "title": "Lambda Memory Exhaustion Runbook",
            "error_pattern": error_pattern,
            "steps": [
                "1. Check current memory configuration in Lambda console",
                "2. Review recent deployments for batch size or data volume changes",
                "3. Increase memory from current value — start with 2x current setting",
                "4. If batch size was increased in recent deploy, also reduce it back",
                "5. Monitor for 5 minutes and verify error rate drops",
            ],
            "recommended_action": "update_lambda_config",
            "risk_level": "low",   # Reversible, no data loss risk
            "estimated_fix_time_minutes": 2,
        }

    elif scenario == "external_dependency":
        return {
            "found": True,
            "title": "External Dependency Degradation Runbook",
            "error_pattern": error_pattern,
            "steps": [
                "1. Confirm degradation is AWS-side via service health dashboard",
                "2. Check if caching can absorb the latency for read-heavy paths",
                "3. Consider circuit breaker to fail fast instead of timeout",
                "4. If latency is > 30s, disable feature and show degraded mode",
                "5. Monitor AWS status page and re-enable when resolved",
            ],
            "recommended_action": "enable_response_cache",
            "risk_level": "medium",  # Cache may serve stale data
            "estimated_fix_time_minutes": 5,
        }

    elif scenario == "cascading_failure":
        return {
            "found": True,
            "title": "DynamoDB Throughput Exhaustion + Retry Storm Runbook",
            "error_pattern": error_pattern,
            "steps": [
                "1. STOP THE BLEEDING: Pause SQS consumer to halt retry storm immediately",
                "2. Scale DynamoDB write capacity to 2x current provisioned units",
                "3. Wait for DynamoDB scaling to complete (~2-3 minutes)",
                "4. Resume SQS consumer at 20% normal concurrency",
                "5. Monitor write capacity utilisation — scale further if needed",
                "6. Investigate what caused the write spike (new feature? traffic surge?)",
            ],
            "recommended_action": "pause_sqs_then_scale_dynamo",
            "risk_level": "high",   # Pausing consumer stops message processing
            "estimated_fix_time_minutes": 10,
            "cost_impact": "~$12/month increase in DynamoDB provisioned capacity",
        }

    return {"found": False, "title": None, "steps": [], "recommended_action": None, "risk_level": "unknown"}


# ── Fix Action Tools ───────────────────────────────────────────────────────────

@tool
def update_lambda_config(function_name: str, memory_mb: int, timeout_sec: int) -> dict:
    """Update Lambda function memory and timeout configuration."""
    return {
        "success": True,
        "function_name": function_name,
        "previous_config": {"memory_mb": 512, "timeout_sec": 30},
        "new_config": {"memory_mb": memory_mb, "timeout_sec": timeout_sec},
        "applied_at": "2024-01-15T10:31:00Z",
    }


@tool
def trigger_lambda_redeploy(function_name: str) -> dict:
    """Trigger a fresh deployment of a Lambda function."""
    return {
        "success": True,
        "function_name": function_name,
        "deploy_id": "d-3K9XQP2R",
        "estimated_time_sec": 45,
        "triggered_at": "2024-01-15T10:31:00Z",
    }


@tool
def enable_response_cache(service: str, ttl_seconds: int = 300) -> dict:
    """Enable response caching for a service to reduce dependency load."""
    return {
        "success": True,
        "service": service,
        "ttl_seconds": ttl_seconds,
        "cache_hit_rate_estimate_pct": 68,
        "estimated_latency_reduction_pct": 65,
        "enabled_at": "2024-01-15T10:31:00Z",
    }


@tool
def pause_sqs_consumer(queue_name: str) -> dict:
    """Pause SQS queue consumer to stop a retry storm."""
    return {
        "success": True,
        "queue_name": queue_name,
        "messages_in_flight": 1200,
        "consumer_status": "paused",
        "paused_at": "2024-01-15T10:31:00Z",
        "note": "Resume with resume_sqs_consumer once DynamoDB capacity is scaled",
    }


@tool
def increase_dynamo_capacity(table_name: str, read_units: int, write_units: int) -> dict:
    """Increase DynamoDB provisioned read/write capacity units."""
    return {
        "success": True,
        "table_name": table_name,
        "previous_read_units": 100,
        "previous_write_units": 200,
        "new_read_units": read_units,
        "new_write_units": write_units,
        "cost_delta_usd_per_month": round((write_units - 200) * 0.00065 * 730, 2),
        "scaling_time_estimate_sec": 180,
        "initiated_at": "2024-01-15T10:31:00Z",
    }


@tool
def verify_fix(service: str) -> dict:
    """Re-check service metrics after a fix has been applied."""
    scenario = get_scenario()

    if scenario == "auto_fix":
        return {
            "service": service,
            "error_rate_pct": 0.2,
            "latency_p99_ms": 1800,
            "status": "healthy",
            "improvement": "Error rate dropped from 8.3% to 0.2%. Latency normalised.",
        }

    elif scenario == "external_dependency":
        return {
            "service": service,
            "error_rate_pct": 2.0,
            "latency_p99_ms": 1100,   # Cache is absorbing most requests
            "status": "mitigated",
            "improvement": "Latency dropped from 31000ms to 1100ms due to cache. AWS issue still ongoing.",
        }

    elif scenario == "cascading_failure":
        return {
            "service": service,
            "error_rate_pct": 0.8,
            "latency_p99_ms": 420,
            "status": "healthy",
            "improvement": "DynamoDB write capacity normalised. Queue draining. Error rate fell from 23% to 0.8%.",
        }

    return {"status": "unknown"}


# ── All tools as a flat list (for registering with LangGraph) ─────────────────

ALL_TOOLS = [
    fetch_recent_logs,
    get_error_metrics,
    check_queue_depth,
    get_dependency_health,
    check_recent_deployments,
    check_aws_service_health,
    get_dynamodb_metrics,
    fetch_runbook,
    update_lambda_config,
    trigger_lambda_redeploy,
    enable_response_cache,
    pause_sqs_consumer,
    increase_dynamo_capacity,
    verify_fix,
]
