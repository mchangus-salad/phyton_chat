def route_requests(workers, requests):
    """
    Return a round-robin routing map for active workers only.
    Each request should be assigned to exactly one active worker.
    """
    active_workers = [worker for worker in workers if worker["active"]] # crear esta lista es redundante y ocupa memoria y procesamiento innecesario, el dict de routes se pueden crear directamente usando la condicion esta.

    if not active_workers:
        return {}

    routes = {worker["id"]: [] for worker in active_workers}
    if not routes:
        return {}

    index = 0
    for request in requests:
        worker = active_workers[index % len(active_workers)] # el calculo debe de ser con el len, no restando 1, este bug hace que no se tome en cuenta el ultimo worker, este es el bug en la logica de round-robin
        routes[worker["id"]].append(request) # este operador esta convirtiendo el string en un string array, esto tiende a confundir a un C# developer, se debe de usar .append(request)
        index += 1
    return routes


def main():
    workers = [
        {"id": "w1", "active": True},
        {"id": "w2", "active": True},
        {"id": "w3", "active": False},
        {"id": "w4", "active": True},
    ]

    requests = ["r1", "r2", "r3", "r4", "r5", "r6"]

    result = route_requests(workers, requests)
    print(result)


if __name__ == "__main__":
    main()