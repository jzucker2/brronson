"""Shared utilities for tests"""


def normalize_path_for_metrics(path):
    """Normalize a path for Prometheus metrics label comparison (strip /private prefix if present)."""
    p = str(path)
    if p.startswith("/private/var/"):
        return p[len("/private") :]
    return p


def assert_metric_with_labels(metrics_text, metric_name, labels, value):
    """
    Assert that a Prometheus metric with the given name, labels (dict), and value exists in the metrics_text.
    Ignores label order.
    """
    for line in metrics_text.splitlines():
        if not line.startswith(metric_name + "{"):
            continue
        if (
            all(f'{k}="{v}"' in line for k, v in labels.items())
            and f"}} {value}" in line
        ):
            return
    raise AssertionError(
        f"Metric {metric_name} with labels {labels} and value {value} not found in metrics output!\nLine examples:\n"
        + "\n".join(
            [line for line in metrics_text.splitlines() if metric_name in line]
        )
    )
