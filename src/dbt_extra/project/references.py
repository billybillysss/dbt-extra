"""Resolve literal dbt references against the project's resource snapshot."""


def resolve_ref(project, ref):
    if ref.kind == "this":
        return None
    if ref.kind == "source":
        candidates = [r for r in project.resources.values() if r.kind == "source" and r.id.endswith("." + ".".join(ref.args))]
    else:
        package = ref.args[0] if len(ref.args) == 2 else None
        candidates = [r for r in project.resources.values() if r.kind in {"model", "seed", "snapshot"}
                      and r.name == ref.args[-1] and (package is None or r.package == package)]
        if ref.version is not None:
            candidates = [r for r in candidates if str(r.node.get("version")) == str(ref.version)]
        else:
            current = [r for r in candidates if r.node.get("version") in {None, r.node.get("latest_version")}]
            candidates = current or candidates
        local = [r for r in candidates if r.package == project.name]
        if package is None and local:
            candidates = local
    return candidates[0] if len(candidates) == 1 else None
