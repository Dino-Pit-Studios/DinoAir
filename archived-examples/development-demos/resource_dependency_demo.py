"""
Resource Manager Dependency Resolution Example

This example demonstrates the enhanced dependency resolution capabilities
of the ResourceManager for complex shutdown ordering.
"""

from utils.resource_manager import ResourceManager, ResourceState, ResourceType


def demonstrate_dependency_resolution():
    """
    Demonstrate the dependency resolution system with a realistic scenario.

    Scenario: Web application with database, cache, web server, and background workers
    Dependencies:
    - Workers depend on Database and Cache
    - Web Server depends on Database and Cache
    - Cache can be independent
    - Database should be shut down last

    Expected shutdown order:
    1. Workers (depend on DB + Cache)
    2. Web Server (depends on DB + Cache)
    3. Cache (no dependencies)
    4. Database (everything depends on it)
    """

    rm = ResourceManager()

    # Register resources with different priorities and dependencies

    # Database - highest priority (shutdown last), no dependencies
    rm.register_resource(
        resource_id="database",
        resource={"type": "postgresql", "host": "localhost"},
        resource_type=ResourceType.DATABASE,
        priority=100,  # High number = shutdown later
        dependencies=[],
        metadata={"critical": True},
    )

    # Cache - medium priority, no dependencies
    rm.register_resource(
        resource_id="cache",
        resource={"type": "redis", "host": "localhost"},
        resource_type=ResourceType.DATABASE,
        priority=50,
        dependencies=[],
        metadata={"critical": False},
    )

    # Web Server - depends on database and cache
    rm.register_resource(
        resource_id="web_server",
        resource={"type": "flask", "port": 8080},
        resource_type=ResourceType.NETWORK,
        priority=30,
        dependencies=["database", "cache"],
        metadata={"public_facing": True},
    )

    # Background Worker 1 - depends on database
    rm.register_resource(
        resource_id="worker_1",
        resource={"type": "celery_worker", "queue": "high_priority"},
        resource_type=ResourceType.THREAD,
        priority=20,
        dependencies=["database"],
        metadata={"queue": "high_priority"},
    )

    # Background Worker 2 - depends on database and cache
    rm.register_resource(
        resource_id="worker_2",
        resource={"type": "celery_worker", "queue": "low_priority"},
        resource_type=ResourceType.THREAD,
        priority=20,
        dependencies=["database", "cache"],
        metadata={"queue": "low_priority"},
    )

    # File Logger - no dependencies, should shutdown early
    rm.register_resource(
        resource_id="file_logger",
        resource={"type": "file_handler", "path": "/var/log/app.log"},
        resource_type=ResourceType.FILE_HANDLE,
        priority=10,  # Low number = shutdown first
        dependencies=[],
        metadata={"log_level": "INFO"},
    )

    # Mark all resources as active for demonstration
    for resource_info in rm.list_resources():
        resource_info.state = ResourceState.ACTIVE

    print("=== Resource Dependency Resolution Demonstration ===")
    print()

    # Show dependency graph
    print("Dependency Graph:")
    dep_graph = rm.get_dependency_graph()
    for resource_id, deps in dep_graph.items():
        deps_str = ", ".join(deps) if deps else "None"
        print(f"  {resource_id} depends on: {deps_str}")
    print()

    # Validate dependencies
    print("Dependency Validation:")
    validation = rm.validate_dependencies()
    print(f"  Valid: {validation['valid']}")
    print(f"  Issues: {validation['issues'] or 'None'}")
    print(f"  Total Resources: {validation['total_resources']}")
    print(f"  Total Dependencies: {validation['total_dependencies']}")
    print()

    # Calculate shutdown order
    print("Calculated Shutdown Order:")
    shutdown_order = rm.calculate_shutdown_order()
    for i, resource in enumerate(shutdown_order, 1):
        deps_str = ", ".join(resource.dependencies) if resource.dependencies else "None"
        print(f"  {i}. {resource.resource_id} (priority: {resource.priority}, deps: {deps_str})")
    print()

    # Test adding a circular dependency
    print("Testing Circular Dependency Detection:")
    print("  Adding circular dependency: database -> worker_1...")
    success = rm.add_resource_dependency("database", "worker_1")
    print(f"  Success: {success} (should be False due to circular dependency)")

    # Revalidate after attempted circular dependency
    validation_after = rm.validate_dependencies()
    print(f"  Still valid: {validation_after['valid']}")
    print()

    # Test removing a dependency
    print("Testing Dependency Removal:")
    print("  Removing dependency: worker_2 -> cache...")
    removed = rm.remove_resource_dependency("worker_2", "cache")
    print(f"  Removed: {removed}")

    # Show updated shutdown order
    print("  Updated shutdown order:")
    new_order = rm.calculate_shutdown_order()
    for i, resource in enumerate(new_order, 1):
        deps_str = ", ".join(resource.dependencies) if resource.dependencies else "None"
        print(f"    {i}. {resource.resource_id} (deps: {deps_str})")
    print()

    print("=== Demonstration Complete ===")

    return {
        "initial_order": [r.resource_id for r in shutdown_order],
        "validation": validation,
        "circular_dependency_prevented": not success,
        "final_order": [r.resource_id for r in new_order],
    }


def demonstrate_complex_scenario():
    """Demonstrate a more complex scenario with multiple dependency levels."""
    rm = ResourceManager()

    # Create a multi-tier application scenario
    resources = [
        # Infrastructure Layer (shutdown last)
        ("config_service", ResourceType.CUSTOM, 200, []),
        ("database", ResourceType.DATABASE, 190, ["config_service"]),
        ("message_queue", ResourceType.NETWORK, 180, ["config_service"]),
        # Service Layer
        ("user_service", ResourceType.CUSTOM, 100, ["database"]),
        ("notification_service", ResourceType.CUSTOM, 100, ["database", "message_queue"]),
        ("auth_service", ResourceType.CUSTOM, 90, ["database"]),
        # Application Layer
        ("api_gateway", ResourceType.NETWORK, 50, ["user_service", "auth_service"]),
        ("web_ui", ResourceType.GUI_COMPONENT, 40, ["api_gateway"]),
        # Monitoring and Logging (shutdown first)
        ("metrics_collector", ResourceType.CUSTOM, 10, ["database"]),
        ("log_aggregator", ResourceType.FILE_HANDLE, 5, []),
    ]

    for resource_id, resource_type, priority, deps in resources:
        rm.register_resource(
            resource_id=resource_id,
            resource={"name": resource_id},
            resource_type=resource_type,
            priority=priority,
            dependencies=deps,
            metadata={"tier": "multi-tier-app"},
        )

    # Mark all as active
    for resource_info in rm.list_resources():
        resource_info.state = ResourceState.ACTIVE

    print("=== Complex Multi-Tier Application Shutdown ===")

    # Show the calculated order
    shutdown_order = rm.calculate_shutdown_order()
    print("Shutdown Order (with dependency resolution):")
    for i, resource in enumerate(shutdown_order, 1):
        deps_str = ", ".join(resource.dependencies) if resource.dependencies else "None"
        tier = (
            "Application"
            if resource.priority < 60
            else "Service"
            if resource.priority < 150
            else "Infrastructure"
        )
        print(f"  {i:2d}. {resource.resource_id:<20} (tier: {tier:<13}, deps: {deps_str})")

    # Compare with priority-only ordering
    priority_order = sorted(rm.list_resources(), key=lambda r: r.priority)
    print("\nPriority-Only Order (for comparison):")
    for i, resource in enumerate(priority_order, 1):
        deps_str = ", ".join(resource.dependencies) if resource.dependencies else "None"
        print(
            f"  {i:2d}. {resource.resource_id:<20} (priority: {resource.priority:3d}, deps: {deps_str})"
        )

    return shutdown_order


if __name__ == "__main__":
    # Run the demonstrations
    print("Running Resource Manager Dependency Resolution Examples\\n")

    try:
        # Basic demonstration
        basic_results = demonstrate_dependency_resolution()
        print(f"\\nBasic demo results: {basic_results}\\n")

        # Complex demonstration
        print("\\n" + "=" * 60 + "\\n")
        complex_order = demonstrate_complex_scenario()

        print(f"\\nComplex demo completed with {len(complex_order)} resources ordered.")

    except Exception as e:
        print(f"Error during demonstration: {e}")
        import traceback

        traceback.print_exc()
