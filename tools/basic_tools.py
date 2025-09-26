"""
Basic tool functions for DinoAir agent integration

This module provides fundamental tool functions that can be discovered and used
by agents for enhanced AI assistance capabilities.

All tool functions must have descriptive docstrings with parameter and return
type documentation for proper discovery by the agent system.
"""

import datetime
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

from utils.process import safe_run

from .common.result import build_success
from .common.validators import validate_path_exists
from .file_search_tool import FILE_SEARCH_TOOLS

# Import the new AI-accessible tool modules
from .notes_tool import NOTES_TOOLS
from .projects_tool import PROJECTS_TOOLS

# Import secure process utilities
try:
    from utils.process import SecurityConfig

    _security_config = SecurityConfig()

    def get_allowed_binaries() -> set[str]:
        """Get the current allowlist from configuration."""
        return _security_config.get_allowed_binaries()

except ImportError:
    # Fallback for when secure_process is not available
    _security_config = None

    def get_allowed_binaries() -> set[str]:
        """Fallback allowlist when configuration is not available."""
        return {
            "dir",
            "ls",
            "pwd",
            "whoami",
            "echo",
            "cat",
            "head",
            "tail",
            "find",
            "grep",
            "wc",
            "sort",
            "uniq",
            "date",
            "hostname",
            "ping",
            "curl",
            "wget",
            "git",
            "npm",
            "pip",
            "python",
            "python.exe",
            "node",
            "node.exe",
            "sqlite3",
        }


# Maintain backward compatibility
ALLOWED_BINARIES = get_allowed_binaries()


def add_two_numbers(a: float, b: float) -> dict[str, Any]:
    """
    Add two numbers together and return the result.

    This is a basic mathematical operation tool that demonstrates
    proper tool function structure with comprehensive documentation.

    Args:
        a (float): The first number to add
        b (float): The second number to add

    Returns:
        Dict[str, Any]: A dictionary containing:
            - result (float): The sum of the two numbers
            - operation (str): Description of the operation performed
            - success (bool): Whether the operation was successful

    Example:
        >>> add_two_numbers(5.0, 3.0)
        {'result': 8.0, 'operation': 'addition', 'success': True}
    """
    try:
        result = a + b
        return {"result": result, "operation": f"{a} + {b} = {result}", "success": True}
    except Exception as e:
        return {
            "result": None,
            "operation": f"Failed to add {a} + {b}",
            "success": False,
            "error": str(e),
        }


def get_current_time() -> dict[str, Any]:
    """
    Get the current date and time in multiple formats.

    Returns comprehensive time information including local time,
    UTC time, and formatted strings for various use cases.

    Returns:
        Dict[str, Any]: A dictionary containing:
            - local_time (str): Local time in ISO format
            - utc_time (str): UTC time in ISO format
            - formatted_time (str): Human-readable local time
            - timestamp (float): Unix timestamp
            - success (bool): Whether the operation was successful

    Example:
        >>> get_current_time()
        {
            'local_time': '2025-01-05T15:30:00.123456',
            'utc_time': '2025-01-05T20:30:00.123456Z',
            'formatted_time': 'January 5, 2025 at 3:30 PM',
            'timestamp': 1736106600.123456,
            'success': True
        }
    """
    try:
        now_local = datetime.datetime.now()
        now_utc = datetime.datetime.utcnow()

        return {
            "local_time": now_local.isoformat(),
            "utc_time": now_utc.isoformat() + "Z",
            "formatted_time": now_local.strftime("%B %d, %Y at %I:%M %p"),
            "timestamp": now_local.timestamp(),
            "success": True,
        }
    except Exception as e:
        return {
            "local_time": None,
            "utc_time": None,
            "formatted_time": None,
            "timestamp": None,
            "success": False,
            "error": str(e),
        }


def list_directory_contents(path: str = ".") -> dict[str, Any]:
    """
    List the contents of a directory with detailed information.

    Provides comprehensive directory listing including file types,
    sizes, and modification times for better file system navigation.

    Args:
        path (str): The directory path to list (defaults to current directory)

    Returns:
        Dict[str, Any]: A dictionary containing:
            - files (List[Dict]): List of files with details
            - directories (List[Dict]): List of subdirectories with details
            - total_items (int): Total number of items found
            - path (str): The path that was listed
            - success (bool): Whether the operation was successful

    Example:
        >>> list_directory_contents("/home/user")
        {
            'files': [{'name': 'file.txt', 'size': 1024,
                      'modified': '2025-01-05T15:30:00'}],
            'directories': [{'name': 'Documents',
                           'modified': '2025-01-05T10:00:00'}],
            'total_items': 2,
            'path': '/home/user',
            'success': True
        }
    """
    try:
        try:
            path_obj = validate_path_exists(path, must_be_dir=True)
        except ValueError as ve:
            # Preserve exact error shapes/messages
            return {
                "files": [],
                "directories": [],
                "total_items": 0,
                "path": str(path),
                "success": False,
                "error": str(ve),
            }

        files: list[dict[str, Any]] = []
        directories: list[dict[str, Any]] = []

        for item in path_obj.iterdir():
            st = item.stat()
            modified_time = datetime.datetime.fromtimestamp(st.st_mtime).isoformat()

            if item.is_file():
                files.append(
                    {
                        "name": item.name,
                        "modified": modified_time,
                        "size": st.st_size,
                    }
                )
            elif item.is_dir():
                directories.append(
                    {
                        "name": item.name,
                        "modified": modified_time,
                    }
                )

        payload = {
            "files": sorted(files, key=lambda x: x["name"]),
            "directories": sorted(directories, key=lambda x: x["name"]),
            "total_items": len(files) + len(directories),
            "path": str(path_obj.absolute()),
            "success": True,
        }
        return build_success(payload)
    except Exception as e:
        return {
            "files": [],
            "directories": [],
            "total_items": 0,
            "path": str(path),
            "success": False,
            "error": str(e),
        }


def read_text_file(file_path: str, encoding: str = "utf-8") -> dict[str, Any]:
    """
    Read the contents of a text file safely with error handling.

    Reads text files with proper encoding handling and provides
    comprehensive error reporting for file operations.

    Args:
        file_path (str): Path to the text file to read
        encoding (str): File encoding (defaults to utf-8)

    Returns:
        Dict[str, Any]: A dictionary containing:
            - content (str): The file contents
            - file_path (str): The path that was read
            - size (int): File size in bytes
            - lines (int): Number of lines in the file
            - encoding (str): Encoding used to read the file
            - success (bool): Whether the operation was successful

    Example:
        >>> read_text_file("config.txt")
        {
            'content': 'Configuration data...',
            'file_path': '/path/to/config.txt',
            'size': 1024,
            'lines': 25,
            'encoding': 'utf-8',
            'success': True
        }
    """

    def _count_lines(content: str) -> int:
        return content.count("\n") + 1 if content else 0

    try:
        try:
            file_path_obj = validate_path_exists(file_path, must_be_file=True)
        except ValueError as ve:
            msg = str(ve)
            # Preserve exact external messages:
            # - Non-existent path must read "File does not exist: {file_path}"
            if msg.startswith("Path does not exist: "):
                err = f"File does not exist: {file_path}"
            else:
                err = msg
            return {
                "content": "",
                "file_path": str(file_path),
                "size": 0,
                "lines": 0,
                "encoding": encoding,
                "success": False,
                "error": err,
            }

        if "../" in str(file_path_obj) or "..\\" in str(file_path_obj):
            raise Exception("Invalid file path")
        with open(file_path_obj, encoding=encoding) as f:
            content = f.read()

        lines = _count_lines(content)
        size = file_path_obj.stat().st_size

        payload = {
            "content": content,
            "file_path": str(file_path_obj.absolute()),
            "size": size,
            "lines": lines,
            "encoding": encoding,
            "success": True,
        }
        return build_success(payload)
    except UnicodeDecodeError as e:
        return {
            "content": "",
            "file_path": str(file_path),
            "size": 0,
            "lines": 0,
            "encoding": encoding,
            "success": False,
            "error": f"Encoding error: {e}",
        }
    except Exception as e:
        return {
            "content": "",
            "file_path": str(file_path),
            "size": 0,
            "lines": 0,
            "encoding": encoding,
            "success": False,
            "error": str(e),
        }


def execute_system_command(command: str, timeout: int = 30) -> dict[str, Any]:
    """
    Execute a system command safely with timeout protection.

    Security:
    - Requires a command string that will be split into a list via shlex.split
    - No shell is used
    - The binary is enforced against a static allowlist (ALLOWED_BINARIES)
    """
    start_time = datetime.datetime.now()

    try:
        if not isinstance(command, str) or not command.strip():
            return {
                "stdout": "",
                "stderr": "Command cannot be empty",
                "return_code": -1,
                "command": command,
                "execution_time": 0,
                "success": False,
                "error": "Command cannot be empty",
            }

        try:
            parts = shlex.split(command)
        except ValueError as e:
            return {
                "stdout": "",
                "stderr": f"Invalid command syntax: {str(e)}",
                "return_code": -1,
                "command": command,
                "execution_time": 0,
                "success": False,
                "error": f"Invalid command syntax: {str(e)}",
            }

        if not parts:
            return {
                "stdout": "",
                "stderr": "Command cannot be empty",
                "return_code": -1,
                "command": command,
                "execution_time": 0,
                "success": False,
                "error": "Command cannot be empty",
            }

        proc = safe_run(parts, allowed_binaries=ALLOWED_BINARIES, timeout=timeout, text=True)
        execution_time = (datetime.datetime.now() - start_time).total_seconds()

        return build_success(
            {
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "return_code": proc.returncode,
                "command": command,
                "execution_time": execution_time,
                "success": proc.returncode == 0,
            }
        )

    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "return_code": -1,
            "command": command,
            "execution_time": timeout,
            "success": False,
            "error": f"Command timed out after {timeout} seconds",
        }
    except PermissionError as e:
        execution_time = (datetime.datetime.now() - start_time).total_seconds()
        return {
            "stdout": "",
            "stderr": str(e),
            "return_code": -1,
            "command": command,
            "execution_time": execution_time,
            "success": False,
            "error": str(e),
        }
    except Exception as e:
        execution_time = (datetime.datetime.now() - start_time).total_seconds()
        return {
            "stdout": "",
            "stderr": str(e),
            "return_code": -1,
            "command": command,
            "execution_time": execution_time,
            "success": False,
            "error": str(e),
        }


def create_json_data(data: dict[str, Any], file_path: str | None = None) -> dict[str, Any]:
    r"""
    Create or manipulate JSON data with optional file output.

    Provides JSON data handling capabilities including validation,
    formatting, and optional file persistence for data management tasks.

    Args:
        data (Dict[str, Any]): The data to convert to JSON
        file_path (Optional[str]): Optional path to save the JSON file

    Returns:
        Dict[str, Any]: A dictionary containing:
            - json_string (str): The formatted JSON string
            - data (Dict): The original data
            - file_written (bool): Whether file was written (if path provided)
            - file_path (str): Path where file was written (if applicable)
            - size (int): Size of the JSON string in characters
            - success (bool): Whether the operation was successful

    Example:
        >>> create_json_data({"name": "test", "value": 42}, "output.json")
        {
            'json_string': '{\n  "name": "test",\n  "value": 42\n}',
            'data': {"name": "test", "value": 42},
            'file_written': True,
            'file_path': '/path/to/output.json',
            'size': 35,
            'success': True
        }
    """

    def _write_json_file(path: str, json_string: str) -> str:
        file_path_obj = Path(path)
        if "../" in str(file_path_obj) or "..\\" in str(file_path_obj):
            raise Exception("Invalid file path")
        file_path_obj.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path_obj, "w", encoding="utf-8") as f:
            f.write(json_string)
        return str(file_path_obj.absolute())

    try:
        # Convert to JSON with pretty formatting
        json_string = json.dumps(data, indent=2, ensure_ascii=False)

        result = {
            "json_string": json_string,
            "data": data,
            "file_written": False,
            "file_path": file_path,
            "size": len(json_string),
            "success": True,
        }

        # Write to file if path provided
        if file_path:
            abs_path = _write_json_file(str(file_path), json_string)
            result["file_written"] = True
            result["file_path"] = abs_path

        return build_success(result)

    except Exception as e:
        return {
            "json_string": "",
            "data": data,
            "file_written": False,
            "file_path": file_path,
            "size": 0,
            "success": False,
            "error": str(e),
        }


# Tool registry for discovery
AVAILABLE_TOOLS = {
    # Basic utility tools
    "add_two_numbers": add_two_numbers,
    "get_current_time": get_current_time,
    "list_directory_contents": list_directory_contents,
    "read_text_file": read_text_file,
    "execute_system_command": execute_system_command,
    "create_json_data": create_json_data,
}

# Add AI-accessible GUI tool wrappers
AVAILABLE_TOOLS.update(NOTES_TOOLS)
AVAILABLE_TOOLS.update(FILE_SEARCH_TOOLS)
AVAILABLE_TOOLS.update(PROJECTS_TOOLS)
