from __future__ import annotations

from pathlib import Path


class ProfileError(Exception):
    """Raised when a benchmark profile cannot be found."""


class ProfileAmbiguousError(ProfileError):
    """Raised when a profile name matches multiple registries."""

    def __init__(self, name: str, matches: list[tuple[str, Path]]):
        self.name = name
        self.matches = matches
        reg_names = [reg for reg, _ in matches]
        super().__init__(
            "Benchmark profile '%s' found in multiple registries: %s. "
            "Use @registry/%s to disambiguate." % (name, ", ".join(reg_names), name)
        )


def find_benchmark_profile(
        name: str,
        config,
        registry_manager=None,
        include_hidden: bool = False,
) -> Path:
    """Find a benchmark profile by name.

    Resolution chain:
    1. Direct file path (contains / or .yaml/.yml extension)
    2. @registry/name scoped lookup
    3. Local benchmarking directory (~/.config/sparkrun/benchmarking/)
    4. Registry search with ambiguity detection

    Args:
        name: Profile name, path, or @registry/name
        config: SparkrunConfig instance
        registry_manager: Optional RegistryManager for registry search
        include_hidden: If True, include hidden registries

    Returns:
        Path to the profile YAML file.

    Raises:
        ProfileError: If profile not found.
        ProfileAmbiguousError: If bare name matches multiple registries.
    """
    # Parse @registry/ prefix
    scoped_registry = None
    lookup_name = name
    if name.startswith("@") and "/" in name:
        prefix, lookup_name = name.split("/", 1)
        scoped_registry = prefix[1:]  # strip @

    # 1. Direct file path
    if "/" in name and not name.startswith("@"):
        direct = Path(name)
        if direct.exists():
            return direct
        # Try with extension
        for ext in (".yaml", ".yml"):
            candidate = Path(name + ext)
            if candidate.exists():
                return candidate
        raise ProfileError("Benchmark profile file not found: %s" % name)

    # 2. Scoped registry lookup
    if scoped_registry and registry_manager:
        matches = registry_manager.find_benchmark_profile_in_registries(
            lookup_name, include_hidden=True,
        )
        scoped_matches = [(reg, path) for reg, path in matches if reg == scoped_registry]
        if scoped_matches:
            return scoped_matches[0][1]
        raise ProfileError(
            "Benchmark profile '%s' not found in registry '%s'" % (lookup_name, scoped_registry)
        )

    # 3. Local benchmarking directory
    local_dir = config.config_path.parent / "benchmarking"
    if local_dir.is_dir():
        for ext in (".yaml", ".yml"):
            candidate = local_dir / (lookup_name + ext)
            if candidate.exists():
                return candidate

    # 4. Registry search with ambiguity detection
    if registry_manager:
        matches = registry_manager.find_benchmark_profile_in_registries(
            lookup_name, include_hidden=include_hidden,
        )
        if len(matches) == 1:
            return matches[0][1]
        elif len(matches) > 1:
            raise ProfileAmbiguousError(lookup_name, matches)

    raise ProfileError("Benchmark profile '%s' not found" % lookup_name)
