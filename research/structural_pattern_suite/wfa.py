from __future__ import annotations


def chronological_folds(sessions: list[str], *, fold_count: int = 5) -> list[dict[str, object]]:
    ordered = sorted(dict.fromkeys(sessions))
    if not ordered:
        return []
    size = max(1, len(ordered) // fold_count)
    folds = []
    for index in range(fold_count):
        start = index * size
        end = len(ordered) if index == fold_count - 1 else min(len(ordered), (index + 1) * size)
        part = ordered[start:end]
        if part:
            folds.append({"fold": index + 1, "start_session": part[0], "end_session": part[-1], "session_count": len(part)})
    return folds

