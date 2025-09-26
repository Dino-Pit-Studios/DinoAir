Usage
=====

Basic usage examples for the utils package.

Dependency Injection
--------------------

.. code-block:: python

   from dependency_container import DependencyContainer

   container = DependencyContainer()
   # Register services
   # Use services

Error Handling
--------------

.. code-block:: python

   from error_handling import handle_errors

   @handle_errors
   def my_function():
       # Function code

Health Checking
---------------

.. code-block:: python

   from health_checker import HealthChecker

   checker = HealthChecker()
   status = checker.check_health()
