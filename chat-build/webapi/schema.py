def exclude_legacy_api_paths(endpoints):
    """Exclude non-versioned legacy API endpoints from OpenAPI generation."""
    filtered = []
    for path, path_regex, method, callback in endpoints:
        if path.startswith('/api/') and not path.startswith('/api/v1/'):
            continue
        filtered.append((path, path_regex, method, callback))
    return filtered
